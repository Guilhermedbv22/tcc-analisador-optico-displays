@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
echo.
echo ÍRIS - PUBLICAR SITE COMPLETO NO NETLIFY
echo.
echo Este publicador envia as paginas e a API de relatorios.
echo Use a conta Netlify que possui o projeto tcc-iris.
echo.
where node >nul 2>&1
if errorlevel 1 (
 echo Instale o Node.js LTS de https://nodejs.org e execute novamente.
 goto erro
)
node -e "if(Number(process.versions.node.split('.')[0])<22)process.exit(1)"
if errorlevel 1 (
 echo Atualize para Node.js LTS 22 ou superior.
 goto erro
)
call npm ci --no-audit --no-fund
if errorlevel 1 goto erro
call npx --no-install netlify login
if errorlevel 1 goto erro
if not exist ".netlify\state.json" (
 echo.
 echo Vincule ao projeto EXISTENTE tcc-iris da sua conta.
 call npx --no-install netlify link --name tcc-iris
 if errorlevel 1 goto erro
)
call npx --no-install netlify deploy --prod --no-build --dir public --functions netlify/functions
if errorlevel 1 goto erro
echo.
echo Publicacao concluida. Abra https://tcc-iris.netlify.app
echo Teste o envio pela aba Publicar no site do Iris Desktop.
pause
popd
exit /b 0
:erro
echo.
echo Publicacao interrompida. Confira a mensagem acima.
pause
popd
exit /b 1
