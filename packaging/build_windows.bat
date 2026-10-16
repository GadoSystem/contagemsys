@echo off
rem Gera o ContagemSys.exe (e o instalador, se o Inno Setup 6 estiver instalado).
rem Uso: clique duas vezes ou rode "packaging\build_windows.bat" na pasta do projeto.
rem Requer Python 3.13 (64 bits) no PATH. Usa um venv proprio: venv-build.
setlocal
cd /d "%~dp0.."

if not exist venv-build\Scripts\python.exe (
    echo Criando venv-build...
    python -m venv venv-build || goto :erro
)

echo Instalando dependencias...
venv-build\Scripts\python -m pip install --upgrade pip || goto :erro
venv-build\Scripts\python -m pip install -r packaging\requirements-desktop.txt || goto :erro

echo Gerando dist\ContagemSys\ContagemSys.exe...
venv-build\Scripts\python -m PyInstaller --noconfirm --clean packaging\ContagemSys.spec || goto :erro

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    echo Gerando instalador...
    "%ISCC%" packaging\instalador.iss || goto :erro
    echo Instalador: dist\ContagemSys-Setup.exe
) else (
    echo Inno Setup 6 nao encontrado: instalador pulado. A pasta dist\ContagemSys ja funciona.
)

echo.
echo Pronto. Teste com: dist\ContagemSys\ContagemSys.exe
pause
exit /b 0

:erro
echo.
echo Falha no build. Veja a mensagem acima.
pause
exit /b 1
