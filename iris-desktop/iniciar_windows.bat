@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 py -3.11 -m venv .venv
  if errorlevel 1 goto erro
)
".venv\Scripts\python.exe" -c "import PySide6, pyqtgraph, numpy, scipy, serial, matplotlib" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto erro
)
".venv\Scripts\python.exe" -m iris_desktop
if errorlevel 1 goto erro
popd
exit /b 0
:erro
echo Nao foi possivel iniciar. Confira Python 3.11/3.12 de 64 bits e as mensagens acima.
pause
popd
exit /b 1
