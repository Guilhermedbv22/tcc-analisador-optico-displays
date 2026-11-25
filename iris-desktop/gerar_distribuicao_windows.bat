@echo off
setlocal
pushd "%~dp0"
if not exist ".venv-build\Scripts\python.exe" (
    py -3.12-64 -m venv .venv-build
    if errorlevel 1 goto fail
)
".venv-build\Scripts\python.exe" -m pip install -r packaging\requirements-windows.txt
if errorlevel 1 goto fail
".venv-build\Scripts\python.exe" packaging\build_windows.py %*
if errorlevel 1 goto fail
popd
exit /b 0
:fail
echo Falha na geracao. Consulte docs\WINDOWS.md e a mensagem acima.
popd
exit /b 1
