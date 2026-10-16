"""Descoberta automatica de fontes locais e ONVIF, com atualizacao segura de video.cameras.

Sem misturar indices DSHOW/MSMF (a mesma camera pode ter indices diferentes).
Nao grava senhas RTSP/ONVIF no config.yaml. A descoberta de IP depende de ONVIF
anunciado na LAN ou de URLs de stream informadas em discovery.ip_streams.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path
import re
import socket
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import yaml

from camera_stream import open_video_source, resolve_video_source


WINDOWS_CAMERA_BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}
ONVIF_PROBE = '''<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header><w:MessageID>uuid:{uuid}</w:MessageID>
<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>
<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>'''


def _thumbnail(frame: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame, (40, 30), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small


def probe_capture(cap, samples: int = 8, sample_delay: float = .10,
                  accept_static: bool = False) -> tuple[bool, int, str]:
    """Confirma leitura de frames. Movimento e sinal auxiliar, nao prova de vida.

    Uma camera real pode permanecer imovel por todo o intervalo da sondagem,
    especialmente webcams virtuais (Iriun) e ambientes escuros. A politica
    accept_static deixa ao usuario a decisao de aceitar uma fonte assim.
    """
    previous = None
    valid = 0
    changed = 0
    samples = max(3, min(25, int(samples)))
    for _ in range(samples):
        ok, frame = cap.read()
        if ok and frame is not None and getattr(frame, "size", 0) > 0:
            valid += 1
            current = _thumbnail(frame)
            if previous is not None:
                if float(np.abs(current.astype(np.float32) - previous).mean()) >= .30:
                    changed += 1
            previous = current
        time.sleep(max(0.0, sample_delay))
    if valid < max(3, samples // 2):
        return False, changed, f"captura incompleta ({valid}/{samples} frames)"
    if changed == 0 and not accept_static:
        return False, changed, "imagem sem mudancas; possivel camera virtual sem sinal ou congelada"
    note = " [IMAGEM ESTATICA: confirme se nao e tela de espera]" if changed == 0 else ""
    return True, changed, f"{valid} frames, {changed} atualizacoes visuais{note}"


def validate_capture(cap, samples: int = 8, sample_delay: float = .10,
                     accept_static: bool = False) -> tuple[bool, str]:
    """Compatibilidade com chamadas existentes; retorna sucesso e diagnostico."""
    ok, _changed, msg = probe_capture(cap, samples, sample_delay, accept_static)
    return ok, msg


def preferred_webcam_backends(selected: str = "auto") -> list[str]:
    selected = str(selected).lower()
    if selected in ("dshow", "msmf", "default"):
        return [selected]
    if os.name == "nt":
        return ["dshow", "msmf"]
    return ["default"]


def scan_webcams(options: dict[str, Any], video: dict[str, Any]) -> list[dict[str, Any]]:
    """Valida fontes SIMULTANEAMENTE, nao apenas uma webcam por vez.

    A antiga descoberta abria webcam 0, fechava, abria webcam 1, fechava.
    Ambas podiam funcionar isoladas, mas disputar a mesma camera/USB quando
    ligadas juntas. Mantemos os handles vivos durante a verificacao; um novo
    dispositivo que paralisa um anterior nao e ativado automaticamente.
    """
    max_index = max(1, min(16, int(options.get("max_index", 6))))
    samples = int(options.get("samples", 8))
    accept_static = bool(options.get("accept_static_frames", False))
    backends = preferred_webcam_backends(options.get("backend", "auto"))
    width = int(video.get("width", 640))
    height = int(video.get("height", 480))
    fps = int(video.get("fps", 12))
    fourcc = str(video.get("fourcc", "MJPG"))
    best_found: list[dict[str, Any]] = []
    best_backend = None
    best_score = (-1, -1)
    # So tenta perfil mais leve quando DUAS fontes parecem validas isoladamente,
    # mas a segunda bloqueia a primeira. Nao dobra o scan sem necessidade.
    profiles = [(width, height, fps)]
    tested_low_bandwidth = False
    profile_index = 0
    while profile_index < len(profiles):
        width, height, fps = profiles[profile_index]
        profile_index += 1
        interference_found = False
        for backend in backends:
            # Lista de (indice, cap): as cameras permanecem abertas em paralelo.
            accepted: list[tuple[int, Any]] = []
            motion_by_index: dict[int, int] = {}
            print(f"[descoberta] Teste simultaneo por {backend.upper()}, indices 0..{max_index-1}", flush=True)
            try:
                for index in range(max_index):
                    cap = None
                    try:
                        cap = open_video_source(index, backend=backend,
                                                width=width, height=height, fps=fps,
                                                fourcc=fourcc, open_timeout_ms=1800,
                                                read_timeout_ms=1800)
                        if cap is None:
                            continue
                        valid, motion, reason = probe_capture(cap, samples=samples,
                                                             accept_static=accept_static)
                        if not valid:
                            print(f"[descoberta]   [-] fonte {index}: {reason}", flush=True)
                            continue
                        # Uma segunda camera pode derrubar a primeira ao negociar
                        # largura de banda USB. Espera estabilizar e confere TODAS.
                        time.sleep(0.35)
                        interrupted = []
                        for old_index, old_cap in accepted:
                            alive, _motion, status = probe_capture(old_cap, samples=max(8, samples),
                                                                   sample_delay=.12,
                                                                   accept_static=accept_static)
                            if not alive:
                                interrupted.append((old_index, status))
                        if interrupted:
                            summary = "; ".join(f"{i}: {why}" for i, why in interrupted)
                            interference_found = True
                            print(f"[descoberta]   [!] fonte {index} interfere nas cameras abertas ({summary}); ignorando", flush=True)
                            continue
                        accepted.append((index, cap))
                        motion_by_index[index] = motion
                        cap = None  # ownership transferido; nao fechar no finally
                        print(f"[descoberta]   [OK] fonte {index} simultanea ({backend}): {reason}", flush=True)
                    except (cv2.error, OSError, ValueError) as exc:
                        print(f"[descoberta]   [-] fonte {index}: {type(exc).__name__}", flush=True)
                    finally:
                        if cap is not None:
                            cap.release()
                    time.sleep(.12)

                # Ultima verificacao de todas antes de escrever config.yaml.
                stable = []
                score_motion = 0
                for index, cap in accepted:
                    ok, motion, message = probe_capture(cap, samples=max(6, samples),
                                                        sample_delay=.12,
                                                        accept_static=accept_static)
                    if ok:
                        score_motion += motion + motion_by_index.get(index, 0)
                        stable.append({"source": index, "backend": backend, "kind": "webcam",
                                       "width": width, "height": height, "fps": fps})
                    else:
                        print(f"[descoberta]   [-] fonte {index} parou durante teste conjunto: {message}", flush=True)
                # Mesmo numero de fontes: prioriza backend com video mais vivo.
                # Exemplo: Iriun com 1 mudanca no DSHOW e 5 no MSMF.
                score = (len(stable), score_motion)
                if score > best_score:
                    best_score = score
                    best_found = stable
                    best_backend = backend
            finally:
                for _, cap in accepted:
                    cap.release()
                # Evita reutilizar handle antes de o driver liberar a camera.
                time.sleep(.4)
        if (interference_found and not tested_low_bandwidth
                and options.get("fallback_low_bandwidth", False)
                and (width, height, fps) != (320, 240, 10)):
            print("[descoberta] USB instavel em perfil normal; testando 320x240 a 10 FPS", flush=True)
            profiles.append((320, 240, 10))
            tested_low_bandwidth = True

    if best_backend:
        print(f"[descoberta] Backend selecionado: {best_backend.upper()} ({len(best_found)} fonte(s) simultaneas).", flush=True)
    return best_found


def discover_onvif_xaddrs(timeout_seconds: float = 2.0) -> list[tuple[str, str]]:
    """Descobre servicos ONVIF na rede local (WS-Discovery multicast UDP/3702)."""
    timeout_seconds = max(.4, min(8.0, float(timeout_seconds)))
    payload = ONVIF_PROBE.format(uuid=uuid4()).encode("utf-8")
    services: dict[str, tuple[str, str]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(.25)
        sock.bind(("", 0))
        sock.sendto(payload, ("239.255.255.250", 3702))
        end = time.monotonic() + timeout_seconds
        while time.monotonic() < end:
            try:
                data, peer = sock.recvfrom(32768)
            except socket.timeout:
                continue
            try:
                peer_ip = ipaddress.ip_address(peer[0])
                if not (peer_ip.is_private or peer_ip.is_link_local):
                    continue
                root = ET.fromstring(data)
                for el in root.iter():
                    if el.tag.split("}")[-1] != "XAddrs" or not el.text:
                        continue
                    for candidate in el.text.split():
                        split = urlsplit(candidate)
                        if split.scheme not in ("http", "https"):
                            continue
                        # Evita consultar URL arbitraria indicada em anuncio multicast.
                        if split.hostname != peer[0]:
                            continue
                        services[peer[0]] = (peer[0], candidate)
            except (ET.ParseError, ValueError):
                continue
    except OSError as exc:
        print(f"[descoberta] ONVIF indisponivel nesta rede: {exc}", flush=True)
    finally:
        sock.close()
    return list(services.values())


def resolve_onvif_stream(host: str, xaddr: str, username: str, password: str) -> str | None:
    """Usa onvif-zeep quando instalado para obter um RTSP real do perfil principal."""
    try:
        from onvif import ONVIFCamera  # instalacao opcional: pip install onvif-zeep
    except ImportError:
        print("[descoberta] Instale onvif-zeep para resolver fluxos de cameras ONVIF.")
        return None
    parsed = urlsplit(xaddr)
    try:
        camera = ONVIFCamera(host, parsed.port or 80, username, password)
        media = camera.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            return None
        request = media.create_type("GetStreamUri")
        request.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
        request.ProfileToken = profiles[0].token
        uri = media.GetStreamUri(request).Uri
        return str(uri) if str(uri).startswith(("rtsp://", "rtsps://", "http://", "https://")) else None
    except Exception as exc:
        print(f"[descoberta] ONVIF {host}: stream nao disponivel ({type(exc).__name__}).")
        return None


def ip_streams(discovery: dict[str, Any], previous_cameras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for raw in discovery.get("ip_streams", []) or []:
        if isinstance(raw, str):
            sources.append({"source": raw, "kind": "ip"})
        elif isinstance(raw, dict) and raw.get("url"):
            sources.append({"source": str(raw["url"]), "kind": "ip",
                            "name": raw.get("name"), "username_env": raw.get("username_env"),
                            "password_env": raw.get("password_env")})
    # Nao descartar streams manuais ja inseridos em video.cameras.
    for camera in previous_cameras:
        if isinstance(camera, dict) and isinstance(camera.get("source"), str):
            if re.match(r"^(rtsp|rtsps|https?)://|^\$", camera["source"], re.IGNORECASE):
                sources.append({"source": camera["source"], "kind": "ip",
                                "name": camera.get("name"),
                                "username_env": camera.get("username_env"),
                                "password_env": camera.get("password_env")})
    onvif = discovery.get("onvif", {}) or {}
    if onvif.get("enabled", True):
        user_env = str(onvif.get("username_env", "ONVIF_USERNAME"))
        pass_env = str(onvif.get("password_env", "ONVIF_PASSWORD"))
        user, password = os.getenv(user_env, ""), os.getenv(pass_env, "")
        print("[descoberta] Buscando cameras ONVIF na rede local...", flush=True)
        for host, xaddr in discover_onvif_xaddrs(float(onvif.get("timeout_seconds", 2))):
            url = resolve_onvif_stream(host, xaddr, user, password)
            if url:
                sources.append({"source": url, "kind": "ip", "name": f"Camera IP {host}",
                                "username_env": user_env, "password_env": pass_env})
    # Deduplica URLs repetidas sem transformar senhas em mensagens de log.
    unique = {}
    for item in sources:
        unique.setdefault(item["source"], item)
    return list(unique.values())


def scan_ip_streams(discovery: dict[str, Any], cameras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    seconds = int(discovery.get("ip_probe_timeout_ms", 2200))
    for item in cameras:
        cap = None
        try:
            uri = resolve_video_source(item["source"], item.get("username_env"), item.get("password_env"))
            cap = open_video_source(uri, backend="ffmpeg", open_timeout_ms=seconds,
                                    read_timeout_ms=seconds)
            if cap is None:
                print(f"[descoberta] Stream IP indisponivel: {urlsplit(item['source']).hostname or 'URL configurada'}")
                continue
            # Uma camera fixa pode ter pixels identicos; valida entrega de frames.
            valid, reason = validate_capture(cap, samples=3, sample_delay=.05,
                                             accept_static=True)
            if valid:
                print(f"[descoberta] Stream IP OK: {urlsplit(item['source']).hostname or 'URL configurada'}")
                accepted.append(item)
        except (OSError, cv2.error, ValueError) as exc:
            print(f"[descoberta] Stream IP rejeitado ({type(exc).__name__}).")
        finally:
            if cap is not None:
                cap.release()
    return accepted


def _key(item: dict[str, Any]) -> tuple[str, str]:
    source = item.get("source")
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        return ("webcam", str(int(source)))
    return ("ip", str(source))


def merge_cameras(existing: list[dict[str, Any]], discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conserva os camera IDs/ajustes (e portanto o vinculo com usuarios no Rebano)."""
    existing = [dict(c) for c in existing if isinstance(c, dict) and "source" in c]
    indexed: dict[tuple[str, str], dict[str, Any]] = {_key(c): c for c in existing}
    matched = set()
    used_ids = {str(c.get("id", "")) for c in existing}
    result: list[dict[str, Any]] = []
    for detected in discovered:
        key = _key(detected)
        if key in matched:
            continue
        matched.add(key)
        previous = indexed.get(key)
        if previous:
            row = dict(previous)
        else:
            index = 1
            while f"camera_{index}" in used_ids:
                index += 1
            cam_id = f"camera_{index}"
            used_ids.add(cam_id)
            row = {"id": cam_id, "name": detected.get("name") or f"Camera {index}"}
        row["source"] = detected["source"]
        # Perfil de captura VALIDADO com todas as webcams abertas: sem sobrescrever
        # com configuracao global mais pesada quando a baixa largura de banda funcionou.
        if key[0] == "webcam":
            for setting in ("width", "height", "fps"):
                if setting in detected:
                    row[setting] = detected[setting]
        row["backend"] = detected.get("backend", row.get("backend", "ffmpeg" if key[0] == "ip" else "default"))
        if detected.get("username_env"):
            row["username_env"] = detected["username_env"]
        if detected.get("password_env"):
            row["password_env"] = detected["password_env"]
        if detected.get("name") and not previous:
            row["name"] = detected["name"]
        if isinstance(row.get("name"), str) and "sem sinal" in row["name"].lower():
            row["name"] = re.sub(r"\s*\(?[^()]*sem sinal[^()]*\)?", "", row["name"], flags=re.IGNORECASE).strip() or str(row["id"])
        row["enabled"] = True
        result.append(row)
    for previous in existing:
        if _key(previous) not in matched:
            row = dict(previous)
            row["enabled"] = False
            result.append(row)
    return result


def replace_video_cameras_yaml(config_path: Path, cameras: list[dict[str, Any]]) -> bool:
    """Atualiza APENAS video.cameras (preserva comentarios, model, gate, etc.)."""
    old = config_path.read_text(encoding="utf-8")
    lines = old.splitlines(keepends=True)
    video_start = next((i for i, line in enumerate(lines) if re.match(r"^video:\s*(?:#.*)?$", line)), None)
    if video_start is None:
        raise ValueError("config.yaml sem secao video")
    start = next((i for i in range(video_start + 1, len(lines))
                  if re.match(r"^  cameras:\s*(?:#.*)?$", lines[i])), None)
    if start is None:
        raise ValueError("config.yaml sem secao video.cameras")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].strip() and not lines[i].lstrip().startswith("#")
                and (not lines[i].startswith(" ") or re.match(r"^  [\w-]+:\s*", lines[i]))), len(lines))
    # remove apenas comentarios inseridos dentro do bloco substituido.
    dumped = yaml.safe_dump({"cameras": cameras}, allow_unicode=True, sort_keys=False,
                            default_flow_style=False, width=1000).splitlines()
    block = "".join("  " + line + "\n" for line in dumped)
    new = "".join(lines[:start]) + block + "".join(lines[end:])
    if new == old:
        return False
    tmp = config_path.with_name(config_path.name + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    try:
        yaml.safe_load(tmp.read_text(encoding="utf-8"))
        os.replace(tmp, config_path)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def discover_and_sync(config_path: str | Path) -> list[dict[str, Any]]:
    """Executado ANTES de load_config(), com o dispositivo ainda livre."""
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    discovery = raw.get("discovery") or {}
    video = raw.get("video") or {}
    current = video.get("cameras") or []
    detected = []
    if (discovery.get("webcam") or {}).get("enabled", True):
        detected.extend(scan_webcams(discovery.get("webcam") or {}, video))
    try:
        detected.extend(scan_ip_streams(discovery, ip_streams(discovery, current)))
    except Exception as exc:
        print(f"[descoberta] Falha na busca IP: {exc}", flush=True)
    merged = merge_cameras(current, detected)
    if replace_video_cameras_yaml(path, merged):
        print(f"[descoberta] Configuracao atualizada: {path}", flush=True)
    print(f"[descoberta] {len(detected)} fonte(s) valida(s); {sum(not c['enabled'] for c in merged)} indisponivel(is).", flush=True)
    if not detected:
        print("[descoberta] Nenhuma camera ativa. Verifique permissoes, cabos e streams IP.", flush=True)
    return merged
