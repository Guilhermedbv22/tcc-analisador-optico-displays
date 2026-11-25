# Íris Desktop

O Íris mede a resposta óptica de monitores e compartilha os resultados em [tcc-iris.netlify.app](https://tcc-iris.netlify.app/). O ESP32 recebe o sinal digitalizado pelo MCP3208 e envia as amostras ao aplicativo, que calcula tempo de resposta GtG, ultrapassagem e acomodação.

## Usar o código-fonte

No Windows, abra `iniciar_windows.bat` com Python 3.11 ou 3.12 instalado. Em um ambiente Python já configurado, use `python -m pip install -e .` e `python -m iris_desktop`.

1. Em **Início**, selecione a porta COM e conecte.
2. Em **Nova medição**, registre o monitor e o overdrive. **Preencher dados da tela** consulta o modelo quando informado pelo sistema, a resolução e a frequência.
3. Selecione a tela do estímulo e configure o plano de teste. Posicione a sonda e inicie.
4. Confira a transição, o tempo restante e, ao terminar, abra **Resultados**.
5. Use **Histórico** para abrir ou exportar sessões. Em **Publicar**, salve o pacote ou envie ao site.

A configuração padrão utiliza MCP3208, ganho fixo, 10 kS/s e os critérios existentes do Íris. As condições indicadas pelo operador acompanham a sessão. O modo avançado aplica os ajustes técnicos selecionados e dá acesso a diagnósticos, comparações, campanhas, reanálise e exportações técnicas. Os ensaios salvos e seus arquivos brutos permanecem em `%LOCALAPPDATA%\IrisDesktop` no Windows. Use `--data-dir PASTA` para indicar outra pasta.

- [Guia de uso](docs/INICIO_RAPIDO.md)
- [Geração do instalador e do portátil](docs/WINDOWS.md)
- [Método das medições](docs/METODO.md)
- [Firmware e protocolo](docs/FIRMWARE_PROTOCOLO.md)

## Testes de regressão

Instale `.[dev]` e execute `python -m pytest -q`. Os testes com arquivos de medição histórica exigem que os arquivos originais estejam em uma pasta indicada por `IRIS_TEST_DATA`. A distribuição de código-fonte mantém esses dados fora do ZIP.
