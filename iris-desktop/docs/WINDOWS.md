# Gerar a distribuição do Íris Desktop no Windows

Na primeira vez, instale [Python 3.12 x64](https://www.python.org/downloads/) com o launcher `py` e [Inno Setup 6](https://jrsoftware.org/isdl.php). A geração foi preparada para Windows 10 x64 a partir da versão 1809 e Windows 11 x64.

1. Extraia o código-fonte para uma pasta gravável.
2. Execute `gerar_distribuicao_windows.bat`. O script prepara um ambiente próprio, instala as versões fixadas em `packaging/requirements-windows.txt`, gera a pasta portátil e abre o executável em um teste de inicialização.
3. Localize o ZIP portátil, o instalador e `releases.json` em `dist-windows`. Para gerar só o portátil, execute `gerar_exe_windows.bat`.
4. Para uma nova versão, altere `__version__` em `iris_desktop/__init__.py` e execute o mesmo script. A versão alimenta os metadados, nomes de arquivos e manifesto.
5. Teste instalação, atualização, desinstalação e uma medição física antes de oferecer a versão publicamente.

Se o Inno Setup estiver em uma pasta personalizada, defina `IRIS_ISCC` com o caminho para `ISCC.exe` e execute o script novamente. O instalador atua por usuário. O executável portátil deve ser aberto após extrair a pasta inteira.

Relatórios, configurações e dados brutos ficam em `%LOCALAPPDATA%\IrisDesktop` nas duas distribuições. No aplicativo, acesse **Configurações → Abrir pasta de dados**. O instalador só gerencia a pasta dos binários em `%LOCALAPPDATA%\Programs\IrisDesktop`.

O workflow manual **Distribuição Windows**, em `.github/workflows/windows.yml`, gera os mesmos arquivos e disponibiliza o artefato `IrisDesktop-Windows-x64`. Coloque os arquivos do Desktop na raiz de um repositório GitHub para usar esse workflow. Comece os testes com a distribuição local. Esses binários não têm assinatura Authenticode até que a equipe assine a versão.

O usuário final instala apenas os binários. Se o Windows não reconhecer a porta COM, identifique o conversor da placa e instale o driver [CP210x](https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers) ou [CH340/CH341](https://www.wch-ic.com/downloads/CH341SER_EXE.html), conforme o hardware.
