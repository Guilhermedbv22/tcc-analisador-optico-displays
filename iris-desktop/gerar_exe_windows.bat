@echo off
call "%~dp0gerar_distribuicao_windows.bat" --portable-only
exit /b %errorlevel%
