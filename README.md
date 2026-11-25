# Íris — analisador óptico de displays

O Íris é um projeto de TCC do curso técnico em Automação Industrial do IFPR Campus Campo Largo. O instrumento registra a variação da luz emitida por um monitor durante transições entre tons de cinza. O Íris Desktop comanda os estímulos, recebe as amostras do ESP32 e calcula o tempo de resposta cinza a cinza (GtG), a ultrapassagem (*overshoot*) e o tempo de acomodação. A configuração padrão usa o ADC externo MCP3208 a 10 kS/s em ganho fixo.

| Componente | Conteúdo |
|---|---|
| [Íris Desktop 1.4.0](iris-desktop/) | Aplicação Python/PySide6, aquisição e análise, exportação de ensaios, testes e empacotamento para Windows |
| [Firmware Íris para ESP32](iris-desktop/firmware/iris_esp32/) | Aquisição, protocolo serial e lógica de ajuste automático de ganho |
| [Site Íris 1.3.0](iris-site/) | Catálogo, relatórios individuais e funções de publicação e consulta no Netlify |
| [Protótipo anterior](docs/PROTOTIPO.md) | Aplicação e firmware anteriores, ensaios, auditoria e instruções originais |

O site publicado pode ser consultado em [Íris no Netlify](https://tcc-iris.netlify.app/).

## Executar localmente

**Desktop.** Na pasta [`iris-desktop/`](iris-desktop/), execute `iniciar_windows.bat` com Python 3.11 ou 3.12 instalado. Em um ambiente Python já configurado, execute `python -m pip install -e .` e `python -m iris_desktop`. O [guia de uso](iris-desktop/docs/INICIO_RAPIDO.md) descreve a preparação do ensaio. O [guia para Windows](iris-desktop/docs/WINDOWS.md) explica como gerar o instalador e a distribuição portátil.

**Site.** Na pasta [`iris-site/`](iris-site/), use Node.js 22 ou superior e execute `npm ci`, `npm test` e `npm run dev`. A prévia fica em `http://localhost:3000`. O [guia do Netlify](iris-site/LEIA_PRIMEIRO.md) descreve as funções e como preparar os downloads. O clone contém o manifesto dos downloads. Para servir o instalador e o portátil em uma prévia ou em outro deploy, copie os binários com `scripts/stage-downloads.mjs`, conforme o guia.

## Método, validação e citação

- [Método de medição](iris-desktop/docs/METODO.md), [arquitetura](iris-desktop/docs/ARQUITETURA.md) e [firmware e protocolo](iris-desktop/docs/FIRMWARE_PROTOCOLO.md).
- [Validação de software da entrega 1.0](iris-desktop/docs/VALIDACAO.md). O documento registra resultados e limites daquela entrega. A avaliação física do instrumento depende da montagem e das condições de cada ensaio.
- [Resultados experimentais do protótipo](resultados/) e [acervo inicial do site](iris-site/public/data/). Os testes históricos do Desktop exigem arquivos específicos indicados por `IRIS_TEST_DATA`, conforme o [README do Desktop](iris-desktop/README.md).

Para referenciar o software na monografia, use os créditos de [`CITATION.cff`](CITATION.cff), indique as versões consultadas e use o link permanente do commit correspondente. Os manifestos SHA-256 em cada pasta registram os pacotes recebidos e podem listar artefatos de distribuição externos ao código versionado. O manifesto original do site tem um hash divergente para `public/downloads/releases.json`. Os hashes dos dois binários conferem com o manifesto de downloads.
