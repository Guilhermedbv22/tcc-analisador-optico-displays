# Analisador óptico de displays — TCC

Projeto experimental para estudar o tempo de resposta entre níveis de cinza (G2G) e o overshoot de monitores, usando aquisição óptica com ESP32 e análise em Python.

O computador apresenta os estímulos em tela cheia, solicita capturas pela USB/serial e gera gráficos, matrizes e arquivos CSV. O ESP32 lê o sensor no ADC e informa a duração e a quantidade de amostras de cada captura.

**Estado do projeto:** em desenvolvimento e validação. A [auditoria existente](docs/auditorias/chatgpt/auditoria_tcc/relatorio_auditoria.md), produzida no contexto das discussões no ChatGPT, registra limitações do algoritmo e da aquisição. Os resultados arquivados são experimentais. A organização deste repositório preserva a lógica original do analisador e do firmware.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `analisador.py` | Aplicação principal: configuração, aquisição, cálculo e gráficos |
| `medidor/medidor.ino` | Firmware atual do ESP32 (Arduino/C++) |
| `analisador.spec` | Configuração existente do PyInstaller |
| `requirements.txt` | Dependências da aplicação principal |
| `legado/` | Scripts e firmware dos primeiros experimentos |
| `dados/ruido/` | Capturas antigas de diagnóstico de ruído |
| `resultados/` | Ensaios exportados, com dados e imagens |
| `docs/auditorias/chatgpt/` | Material original da auditoria, suas entradas e resultados |
| `docs/ORGANIZACAO.md` | Mapa dos arquivos e critérios de organização |
| `docs/VERSIONAMENTO.md` | Como registrar e enviar novas versões |
| `docs/SINCRONIZACAO.md` | Como manter PC e notebook atualizados pelo mesmo repositório |
| `configs/notebook.example.json` | Perfil de configuração recebido do notebook |

## Executar no computador

Use uma instalação do Python com Tkinter e suporte a interface gráfica. Execute os comandos abaixo **na raiz do repositório**, pois a configuração e os resultados são relativos à pasta de execução.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe analisador.py
```

As dependências foram identificadas pelos imports do código; ainda não há versões fixadas a partir de uma instalação validada com o hardware.

1. Grave o firmware no ESP32 e conecte-o por USB.
2. Feche o monitor serial da IDE para liberar a porta.
3. Na aplicação, selecione a porta COM e preencha os dados do monitor e do ensaio.
4. Comece com a janela padrão de 100 ms. O analisador exige ao menos 500 amostras, embora o firmware aceite janelas menores.
5. Examine o teste preliminar e confirme a aquisição completa na interface.

O campo de tempo ligado registra o aquecimento informado pelo operador; o programa não aguarda automaticamente esse período. O teste exibe mudanças de brilho em tela cheia.

A configuração pessoal é salva em `tcc_config.json`, ignorado pelo Git. Há um modelo em `tcc_config.example.json`; a aplicação também cria sua configuração ao iniciar um ensaio.

## Firmware

Abra `medidor/medidor.ino` na IDE Arduino e selecione a placa correspondente ao seu ESP32. O código utiliza a API de timer do **Arduino-ESP32 3.x**, conforme as chamadas presentes no firmware.

- Entrada do sensor: GPIO 34; resolução configurada: 12 bits.
- Comunicação: 115200 baud.
- Período nominal do timer: 100 µs (10 kHz); a leitura acontece no loop principal.
- Captura padrão: 1.000 amostras; capacidade do buffer: 6.000.
- LCD 16×2 I2C habilitado por `TEM_DISPLAY = 1`, endereço `0x27`; inclui `LiquidCrystal_I2C.h` e `Wire.h`.
- Para uma montagem sem LCD, ajuste `TEM_DISPLAY` para `0` antes de compilar.

Esses dados descrevem a configuração do código. A frequência nominal do timer não comprova a regularidade das leituras individuais. Consulte a auditoria para as pendências da montagem e da validação.

### Protocolo serial

| Comando PC → ESP32 | Resposta / efeito |
|---|---|
| `F` | `FW:<versao>` |
| `W:<ms>` | Ajusta a janela e responde `JANELA:<ms>` |
| `T:linha1\|linha2` | Atualiza o LCD, quando habilitado |
| `I` | Inicia uma captura |

Cada mensagem termina com nova linha. Uma captura retorna `META:<duracao_us>,<contagem>`, uma amostra ADC por linha e `FIM`.

## Resultados e auditoria

Cada novo ensaio gera uma pasta em `resultados/`, contendo `resumo.csv`, `config_ensaio.json` e `dashboard.png`. A exportação de `dados_brutos.csv` depende da opção marcada na interface. As células do dashboard permitem abrir as curvas de cada transição.

O ensaio arquivado de 31/08/2026 está em [resultados](resultados/LG_ULTRAGEAR_24GS60F-B_20260831_085241/). As entradas da auditoria são um conjunto preservado à parte e não devem ser substituídas pelos dados desse ensaio.

O [ensaio do notebook](resultados/NOTEBOOK_20260831_162903/) também está preservado, com dados brutos, resumo, configuração e dashboard. A [integração do notebook](docs/SINCRONIZACAO.md) descreve a origem dos arquivos adicionais e a rotina de sincronização.

Para repetir a auditoria offline, em Python 3.10 ou superior:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-auditoria.txt
.\.venv\Scripts\python.exe docs/auditorias/chatgpt/auditoria_tcc/auditar.py --entrada docs/auditorias/chatgpt/auditoria_tcc/entradas --saida .local/auditoria
```

O script registra casos com falhas conhecidas. Sua conclusão sem erro não significa aprovação metrológica. Os relatórios históricos também mencionam documentos externos que não estavam nesta pasta.

## Gerar executável (opcional)

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller analisador.spec
```

O executável fica em `dist/`. Essa pasta e `build/` ficam fora do Git. O arquivo `.spec` foi preservado; a geração do executável precisa ser validada no ambiente de uso.

## Histórico

O primeiro commit registra os arquivos recebidos; o seguinte organiza o material e adiciona esta documentação. Os protótipos anteriores permanecem em `legado/`, mas não existe um histórico Git anterior à importação. Veja o [guia de versionamento](docs/VERSIONAMENTO.md).
