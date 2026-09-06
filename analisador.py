"""
================================================================================
 TCC - ANALISADOR OPTICO DE DISPLAYS (G2G, OVERSHOOT, EXPORTACAO E CONFIG SALVA)
 v3 (definitiva) - timer de hardware no ESP32, tempo real reportado (META),
 display LCD opcional, toggle de curva bruta, estimativa de tempo, exportacao.
================================================================================
"""

import serial
import time
import pygame
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import tkinter as tk
from tkinter import ttk, messagebox
import csv
import json
import os

# ==============================================================================
# CONFIGURACOES METROLOGICAS
# ==============================================================================
ALVOS_RGB = [0, 51, 102, 153, 204, 255]
CORTE_VESA = 0.10
TOLERANCIA_OVERSHOOT = 0.00
ARQUIVO_CONFIG = 'tcc_config.json'

# --- comunicacao com o ESP32 ---
BAUD_RATE = 115200               # tem que bater com o Serial.begin() do firmware
TIMEOUT_CAPTURA = 5.0            # segundos: tempo maximo esperando uma captura completa
TENTATIVAS_POR_REPETICAO = 3     # novas tentativas automaticas se uma captura vier incompleta
MIN_AMOSTRAS_VALIDAS = 500       # captura com menos amostras que isso e descartada
LIMITE_FALHAS_CONSECUTIVAS = 10  # aborta o ensaio se acumular esse tanto de falhas seguidas
JANELA_CAPTURA_MS_PADRAO = 100   # janela de aquisicao pedida ao ESP32 (1000 amostras a 10 kHz)

# --- deteccao de saturacao do sensor/ADC ---
LIMIAR_ADC_BAIXO = 5
LIMIAR_ADC_ALTO = 4090
SATURACAO_FRACAO_LIMIAR = 0.02   # mais de 2% das amostras no limite do ADC = saturado

DADOS_ENSAIO = {}
METADADOS = {}
ESTATISTICAS = {}

# ==============================================================================
# 1. GERENCIAMENTO DE ARQUIVO (SALVAR/CARREGAR CONFIGS)
# ==============================================================================
def carregar_config_salva():
    # Valores padrao de fabrica se for a primeira vez
    config = {'porta': 'COM4', 'monitor': 'LG ULTRAGEAR 24GS60F-B',
              'overdrive': 'Fast', 'warmup': '30', 'repeticoes': '20', 'intervalo': '0.3',
              'janela_captura_ms': str(JANELA_CAPTURA_MS_PADRAO), 'exportar_dados_brutos': False,
              'mostrar_raw': False}
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, 'r') as f:
                config_salva = json.load(f)
                config.update(config_salva)
        except Exception:
            pass
    return config

def salvar_config(config_dict):
    try:
        with open(ARQUIVO_CONFIG, 'w') as f:
            json.dump(config_dict, f)
    except Exception:
        pass

def normalizar_porta(porta):
    porta = porta.strip()
    if porta.lower().startswith('com'):
        return porta.upper()
    return porta

# ==============================================================================
# 2. NUCLEO MATEMATICO E CORRECAO OPTICA
# ==============================================================================
def verificar_saturacao(raw_array, rgb_origem, rgb_destino):
    """Sinaliza quando uma fracao grande das amostras bateu no limite do ADC.
    So faz sentido checar isso em transicoes reais (origem != destino): uma
    celula origem==destino serve so para medir ruido de fundo."""
    if rgb_origem == rgb_destino:
        return False
    raw_array = np.asarray(raw_array)
    n = raw_array.size
    if n == 0:
        return False
    pinados = np.count_nonzero((raw_array <= LIMIAR_ADC_BAIXO) | (raw_array >= LIMIAR_ADC_ALTO))
    return (pinados / n) > SATURACAO_FRACAO_LIMIAR

def processar_curva(dados_brutos, rgb_origem, rgb_destino, tempo_por_amostra_ms):
    voltagens_adc = np.array(dados_brutos, dtype=float)
    saturado = verificar_saturacao(voltagens_adc, rgb_origem, rgb_destino)

    # 1. Correcao do Start (Lendo apenas as 50 primeiras amostras)
    v_start = np.mean(voltagens_adc[:50])
    v_end = np.mean(voltagens_adc[-50:])
    amplitude_raw = v_end - v_start

    # --- FILTRO DE RUIDO (Transicoes iguais ou falsas flutuacoes) ---
    if rgb_origem == rgb_destino or abs(amplitude_raw) < 30:
        escala_ruido = 255.0 / 4095.0
        mapped_signal = rgb_origem + (voltagens_adc - v_start) * escala_ruido
        detalhes = {
            'raw': voltagens_adc, 'rgb_array': mapped_signal,
            'lim_inf': rgb_origem, 'lim_sup': rgb_origem, 'rgb_target': rgb_origem,
            't_inf': 0, 't_sup': 0,
            'tempo_por_amostra_ms': tempo_por_amostra_ms,
            'saturado': saturado
        }
        return 0.0, 0.0, detalhes

    # --- ANALISE G2G REAL (Cortes VESA 10-90%) ---
    v_10 = v_start + (amplitude_raw * CORTE_VESA)
    v_90 = v_start + (amplitude_raw * (1.0 - CORTE_VESA))

    if amplitude_raw > 0:  # Subida
        idx_90 = np.argmax(voltagens_adc >= v_90)
        below_10 = np.where(voltagens_adc[:idx_90] <= v_10)[0]
        idx_10 = below_10[-1] if len(below_10) > 0 else 0

        v_pico = np.max(voltagens_adc)
        overshoot_taxa = (v_pico - v_end) / amplitude_raw
    else:  # Descida
        idx_90 = np.argmax(voltagens_adc <= v_90)
        above_10 = np.where(voltagens_adc[:idx_90] >= v_10)[0]
        idx_10 = above_10[-1] if len(above_10) > 0 else 0

        v_pico = np.min(voltagens_adc)
        overshoot_taxa = (v_pico - v_end) / amplitude_raw

    tempo_resposta = abs(idx_90 - idx_10) * tempo_por_amostra_ms
    overshoot_perc = (overshoot_taxa * 100) if overshoot_taxa >= TOLERANCIA_OVERSHOOT else 0.0

    # --- MAPEAMENTO VISUAL PRECISO ---
    escala_visual = (rgb_destino - rgb_origem) / amplitude_raw
    mapped_signal = rgb_origem + (voltagens_adc - v_start) * escala_visual

    lim_10_visual = rgb_origem + (rgb_destino - rgb_origem) * CORTE_VESA
    lim_90_visual = rgb_origem + (rgb_destino - rgb_origem) * (1.0 - CORTE_VESA)

    detalhes = {
        'raw': voltagens_adc, 'rgb_array': mapped_signal,
        'lim_inf': lim_10_visual, 'lim_sup': lim_90_visual, 'rgb_target': rgb_destino,
        't_inf': idx_10 * tempo_por_amostra_ms, 't_sup': idx_90 * tempo_por_amostra_ms,
        'tempo_por_amostra_ms': tempo_por_amostra_ms,
        'saturado': saturado
    }
    return tempo_resposta, overshoot_perc, detalhes

# ==============================================================================
# 3. PROTOCOLO / COMUNICACAO COM O ESP32
# ==============================================================================
def conectar_esp32(porta):
    """Abre a porta, deixa o ESP32 terminar o boot e confirma que o firmware
    certo esta rodando (handshake) antes de comecar qualquer coisa."""
    esp32 = serial.Serial(porta, BAUD_RATE, timeout=1)
    esp32.setDTR(False)
    esp32.setRTS(False)
    time.sleep(2)
    esp32.reset_input_buffer()
    esp32.write(b"F\n")

    t0 = time.time()
    versao = None
    while time.time() - t0 < 2.0:
        linha = esp32.readline().decode('utf-8', errors='ignore').strip()
        if linha.startswith("FW:"):
            versao = linha[3:]
            break
    if versao is None:
        esp32.close()
        raise RuntimeError(
            "O ESP32 nao respondeu ao handshake.\n\nVerifique se:\n"
            "- a porta serial esta correta\n"
            "- o firmware certo foi gravado no ESP32\n"
            "- nenhum outro programa (Serial Monitor, etc.) esta com a porta aberta"
        )
    return esp32, versao

def configurar_janela_captura(esp32, janela_ms):
    esp32.reset_input_buffer()
    esp32.write(f"W:{int(janela_ms)}\n".encode())
    t0 = time.time()
    while time.time() - t0 < 1.0:
        linha = esp32.readline().decode('utf-8', errors='ignore').strip()
        if linha.startswith("JANELA:"):
            return True
    return False

def capturar_transicao(esp32, tela, rgb_o, rgb_d, tempo_espera):
    """Uma tentativa de captura. Retorna (amostras, duracao_us_reportada, contagem_reportada)."""
    tela.fill((rgb_o, rgb_o, rgb_o))
    pygame.display.flip()
    time.sleep(tempo_espera)

    esp32.reset_input_buffer()
    esp32.write(b'I\n')

    tela.fill((rgb_d, rgb_d, rgb_d))
    pygame.display.flip()

    dados = []
    duracao_us = None
    contagem_esperada = None
    t0 = time.time()
    while True:
        pygame.event.pump()
        try:
            linha = esp32.readline().decode('utf-8', errors='ignore').strip()
        except Exception:
            linha = ""
        if linha:
            if linha.startswith("META:"):
                try:
                    duracao_txt, contagem_txt = linha[5:].split(",")
                    duracao_us = int(duracao_txt)
                    contagem_esperada = int(contagem_txt)
                except (ValueError, IndexError):
                    pass
            elif linha == "FIM":
                break
            elif linha.isdigit():
                dados.append(int(linha))
        if time.time() - t0 > TIMEOUT_CAPTURA:
            break
    return dados, duracao_us, contagem_esperada

def capturar_transicao_valida(esp32, tela, rgb_o, rgb_d, tempo_espera):
    """Repete a captura ate MIN_AMOSTRAS_VALIDAS/contagem baterem, ou desiste.
    Retorna (amostras, tempo_por_amostra_ms) ou (None, None) se falhar em todas as tentativas."""
    for _tentativa in range(TENTATIVAS_POR_REPETICAO):
        dados, duracao_us, contagem_esperada = capturar_transicao(esp32, tela, rgb_o, rgb_d, tempo_espera)
        amostras_ok = len(dados) >= MIN_AMOSTRAS_VALIDAS
        contagem_bate = (contagem_esperada is not None) and (len(dados) == contagem_esperada)
        if amostras_ok and contagem_bate and duracao_us:
            dt_ms = (duracao_us / len(dados)) / 1000.0
            return dados, dt_ms
        time.sleep(0.05)  # pequena pausa antes de tentar de novo
    return None, None

# ==============================================================================
# 4. AQUISICAO
# ==============================================================================
def imprimir_progresso(transicao_atual, total_transicoes, rgb_o, rgb_d, rep, total_reps, inicio_ensaio):
    concluidas = (transicao_atual - 1) * total_reps + (rep - 1)
    total_capturas = total_transicoes * total_reps
    pct = 100.0 * concluidas / total_capturas if total_capturas else 0.0
    decorrido = time.time() - inicio_ensaio
    eta_txt = ""
    if concluidas > 0:
        tempo_por_captura = decorrido / concluidas
        restante_s = tempo_por_captura * (total_capturas - concluidas)
        eta_txt = f" | restante ~{restante_s / 60:.1f} min"
    print(f"\r[{pct:5.1f}%] transicao {transicao_atual:2d}/{total_transicoes} "
          f"({rgb_o:>3}->{rgb_d:<3})  rep {rep:02d}/{total_reps:02d}{eta_txt}   ",
          end="", flush=True)

def teste_preliminar(config, esp32):
    pygame.init()
    tela = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    esp32.write(b"T:  TESTE PREVIO| (RGB 0 -> 153)\n")
    dados, dt_ms = capturar_transicao_valida(esp32, tela, 0, 153, 1.0)
    pygame.quit()

    if dados is None:
        messagebox.showerror(
            "Erro",
            "Falha na captura de teste: o ESP32 nao enviou dados validos.\n"
            "Verifique a conexao serial e se o firmware foi gravado corretamente."
        )
        return False

    t, ov, det = processar_curva(dados, 0, 153, dt_ms)
    saturado = det.get('saturado', False)
    taxa_real = 1000.0 / dt_ms if dt_ms else 0.0

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.canvas.manager.set_window_title("Validacao de Calibracao (Ruido)")
    tempos = np.arange(len(det['raw'])) * dt_ms

    ax.plot(tempos, det['rgb_array'], color='#00ffcc', lw=2, label='Sinal Convertido')
    ax.axhline(det['lim_inf'], color='red', ls='--', alpha=0.5)
    ax.axhline(det['lim_sup'], color='red', ls='--', alpha=0.5)
    ax.axhline(det['rgb_target'], color='#ccff00', alpha=0.4, label='Alvo (153)')
    ax.axvspan(det['t_inf'], det['t_sup'], color='red', alpha=0.2, label=f"Tempo: {t:.2f}ms")

    titulo = f"Teste Preliminar (0 -> 153) | Taxa real: {taxa_real:.0f} Sa/s. Feche para decidir."
    if saturado:
        titulo += "  [!] SINAL SATURADO"
    ax.set_title(titulo)
    ax.set_yticks(ALVOS_RGB)
    ax.set_ylim(-10, 265)
    ax.set_ylabel("Sinal Mapeado (RGB)"); ax.set_xlabel("Tempo (ms)")
    ax.grid(alpha=0.2)

    # Exibe a linha do ADC bruto apenas se a opcao estiver marcada na interface
    if config.get('mostrar_raw'):
        ax2 = ax.twinx()
        ax2.plot(tempos, det['raw'], color='#ff3399', alpha=0.3, label='ADC Bruto')
        ax2.set_ylabel("Bits ADC Brutos", color='#ff3399')
        ax2.set_ylim(0, 4095)
        ax2.legend(loc='upper right')

    ax.legend(loc='lower right')
    plt.tight_layout()
    plt.show()

    if saturado:
        prosseguir = messagebox.askyesno(
            "Sinal saturado",
            "O sinal capturado bateu no limite do ADC (0 ou 4095) numa fracao "
            "significativa das amostras. Isso indica que o ganho/exposicao do "
            "circuito do sensor esta desajustado, e pode distorcer os tempos "
            "calculados no ensaio completo.\n\nDeseja continuar mesmo assim?"
        )
        if not prosseguir:
            return False

    return messagebox.askyesno(
        "Validacao",
        f"Taxa de amostragem real medida: {taxa_real:.0f} Sa/s.\n"
        "O grafico esta correto e o ruido aceitavel?\n"
        "Deseja iniciar a bateria completa?"
    )

def executar_ensaio(config):
    global METADADOS, DADOS_ENSAIO, ESTATISTICAS
    METADADOS = config
    DADOS_ENSAIO.clear()
    ESTATISTICAS.clear()

    porta = normalizar_porta(config['porta'])
    try:
        esp32, versao_fw = conectar_esp32(porta)
        print(f"Conectado ao ESP32 (firmware {versao_fw}) na porta {porta}.")
    except Exception as e:
        messagebox.showerror("Erro de conexao", str(e))
        iniciar_interface()
        return

    janela_ms = float(config.get('janela_captura_ms', JANELA_CAPTURA_MS_PADRAO))
    if not configurar_janela_captura(esp32, janela_ms):
        print("[aviso] ESP32 nao confirmou a janela de captura; seguindo com o padrao do firmware.")

    if not teste_preliminar(config, esp32):
        esp32.close()
        iniciar_interface()
        return

    pygame.init()
    tela = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    todas_transicoes = [(o, d) for o in ALVOS_RGB for d in ALVOS_RGB]
    total_t = len(todas_transicoes)
    repeticoes = int(config['repeticoes'])

    reps_totais_ok = 0
    reps_totais_tentadas = 0
    transicoes_com_saturacao = 0
    falhas_consecutivas = 0
    interrompido = False
    inicio_ensaio = time.time()

    print(f"\n=== Iniciando ensaio: {config['monitor']} ({total_t} transicoes x {repeticoes} repeticoes) ===")

    for transicao_atual, (rgb_o, rgb_d) in enumerate(todas_transicoes, 1):
        tempos = []; overshoots = []; raw_dados = []
        saturacao_nesta_transicao = False

        for rep in range(1, repeticoes + 1):
            reps_totais_tentadas += 1
            imprimir_progresso(transicao_atual, total_t, rgb_o, rgb_d, rep, repeticoes, inicio_ensaio)

            str_linha1 = f"{rgb_o:>3}->{rgb_d:<3} ({transicao_atual}/{total_t})"
            str_linha2 = f"Progresso: {rep:02d}/{repeticoes:02d}"
            esp32.write(f"T:{str_linha1:14}|{str_linha2:14}\n".encode())

            dados, dt_ms = capturar_transicao_valida(esp32, tela, rgb_o, rgb_d, float(config['intervalo']))
            if dados is None:
                falhas_consecutivas += 1
                if falhas_consecutivas >= LIMITE_FALHAS_CONSECUTIVAS:
                    interrompido = True
                    break
                continue
            falhas_consecutivas = 0

            t, ovs, detalhes = processar_curva(dados, rgb_o, rgb_d, dt_ms)
            if detalhes.get('saturado'):
                saturacao_nesta_transicao = True

            tempos.append(t); overshoots.append(ovs); raw_dados.append(detalhes)
            reps_totais_ok += 1

        if tempos:
            DADOS_ENSAIO[(rgb_o, rgb_d)] = {
                'tempo_med': np.mean(tempos),
                'overshoot_med': np.mean(overshoots),
                'reps_validas': len(tempos),
                'reps_total': repeticoes,
                'saturacao': saturacao_nesta_transicao,
                'detalhes_raw': raw_dados
            }
            if saturacao_nesta_transicao:
                transicoes_com_saturacao += 1
        elif not interrompido:
            print(f"\n  [erro] transicao {rgb_o}->{rgb_d}: nenhuma repeticao valida, celula marcada como erro.")

        if interrompido:
            break

    if interrompido:
        pygame.quit()
        esp32.close()
        print(f"\n[ERRO] Ensaio interrompido apos {falhas_consecutivas} falhas de captura consecutivas.")
        messagebox.showerror(
            "Ensaio interrompido",
            f"O ensaio foi interrompido apos {falhas_consecutivas} falhas de captura seguidas — "
            "a conexao com o ESP32 parece ter sido perdida.\n\n"
            "Verifique o cabo USB/porta serial e inicie o ensaio novamente."
        )
        iniciar_interface()
        return

    duracao_total = time.time() - inicio_ensaio
    pct_validas = 100.0 * reps_totais_ok / reps_totais_tentadas if reps_totais_tentadas else 0.0
    print(f"\n=== Ensaio concluido em {duracao_total / 60:.1f} min | "
          f"{reps_totais_ok}/{reps_totais_tentadas} capturas validas ({pct_validas:.0f}%) ===\n")

    pygame.quit()
    esp32.write(b"T:ENSAIO PRONTO| MUITO TOP!   \n")
    esp32.close()

    ESTATISTICAS.update({
        'reps_totais_ok': reps_totais_ok,
        'reps_totais_tentadas': reps_totais_tentadas,
        'transicoes_com_saturacao': transicoes_com_saturacao,
        'duracao_total_s': duracao_total,
    })

    gerar_dashboard_osrtt()

# ==============================================================================
# 5. EXPORTACAO DE RESULTADOS
# ==============================================================================
def normalizar_nome_arquivo(texto):
    texto = texto.strip()
    limpo = [c if (c.isalnum() or c in (' ', '-', '_')) else '_' for c in texto]
    return ''.join(limpo).replace(' ', '_') or 'sessao'

def criar_pasta_sessao(config):
    pasta_base = 'resultados'
    nome_monitor = normalizar_nome_arquivo(config.get('monitor', 'monitor'))
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    pasta = os.path.join(pasta_base, f"{nome_monitor}_{timestamp}")
    os.makedirs(pasta, exist_ok=True)
    return pasta

def exportar_resumo_csv(pasta):
    caminho = os.path.join(pasta, 'resumo.csv')
    with open(caminho, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['origem_rgb', 'destino_rgb', 'g2g_ms', 'overshoot_pct',
                    'repeticoes_validas', 'repeticoes_total', 'saturacao'])
        for origem in ALVOS_RGB:
            for destino in ALVOS_RGB:
                dados = DADOS_ENSAIO.get((origem, destino))
                if dados:
                    w.writerow([origem, destino, f"{dados['tempo_med']:.3f}",
                                f"{dados['overshoot_med']:.2f}", dados['reps_validas'],
                                dados['reps_total'], 'SIM' if dados['saturacao'] else 'NAO'])
                else:
                    w.writerow([origem, destino, '', '', 0, METADADOS.get('repeticoes', ''), ''])
    return caminho

def exportar_dados_brutos_csv(pasta):
    caminho = os.path.join(pasta, 'dados_brutos.csv')
    with open(caminho, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['origem_rgb', 'destino_rgb', 'repeticao', 'indice_amostra', 'tempo_ms', 'adc_bruto'])
        for (origem, destino), dados in DADOS_ENSAIO.items():
            for rep_idx, det in enumerate(dados['detalhes_raw'], start=1):
                dt = det.get('tempo_por_amostra_ms', 0.0)
                for i, valor in enumerate(det['raw']):
                    w.writerow([origem, destino, rep_idx, i, f"{i * dt:.3f}", int(valor)])
    return caminho

def exportar_config_json(pasta):
    caminho = os.path.join(pasta, 'config_ensaio.json')
    dados_serializaveis = {k: v for k, v in METADADOS.items()}
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados_serializaveis, f, indent=2, ensure_ascii=False)
    return caminho

# ==============================================================================
# 6. INTERATIVIDADE E GRAFICO INDIVIDUAL
# ==============================================================================
def abrir_grafico_detalhado(origem, destino):
    dados = DADOS_ENSAIO.get((origem, destino))
    if not dados:
        return
    detalhes = dados['detalhes_raw'][-1]
    dt = detalhes.get('tempo_por_amostra_ms', 0.1)

    fig, ax = plt.subplots(figsize=(10, 5))
    plt.style.use('dark_background')
    fig.canvas.manager.set_window_title(f"Detalhe: {origem} -> {destino}")

    tempos_x = np.arange(len(detalhes['raw'])) * dt

    ax.plot(tempos_x, detalhes['rgb_array'], color='#00ffcc', linewidth=2, label='Sinal Convertido')
    ax.axhline(detalhes['lim_inf'], color='red', linestyle='--', alpha=0.5)
    ax.axhline(detalhes['lim_sup'], color='red', linestyle='--', alpha=0.5)
    ax.axhline(detalhes['rgb_target'], color='#ccff00', alpha=0.4, label='Alvo')

    if origem != destino:
        ax.axvspan(detalhes['t_inf'], detalhes['t_sup'], color='red', alpha=0.2,
                   label=f"Tempo: {dados['tempo_med']:.2f}ms")

    titulo = (f"Transicao: {origem} -> {destino} | Overshoot: {dados['overshoot_med']:.1f}% | "
              f"Reps validas: {dados['reps_validas']}/{dados['reps_total']}")
    if dados.get('saturacao'):
        titulo += " | [!] SATURADO"
    ax.set_title(titulo)
    ax.set_yticks(ALVOS_RGB)
    ax.set_ylim(-10, 265)
    ax.set_ylabel("Sinal Mapeado (RGB)"); ax.set_xlabel("Tempo (ms)")

    # Exibe a linha do ADC bruto apenas se a opcao estiver marcada
    if METADADOS.get('mostrar_raw'):
        ax2 = ax.twinx()
        ax2.plot(tempos_x, detalhes['raw'], color='#ff3399', alpha=0.3, label='Tensao ADC')
        ax2.set_ylabel("Bits ADC Brutos", color='#ff3399')
        ax2.set_ylim(0, 4095)
        ax2.legend(loc='upper right')

    ax.legend(loc='lower right'); ax.grid(alpha=0.2)
    plt.show()

def on_click_matriz(event, eixo, tipo):
    if event.inaxes == eixo:
        x, y = int(round(event.xdata)), int(round(event.ydata))
        if 0 <= x < 6 and 0 <= y < 6:
            abrir_grafico_detalhado(ALVOS_RGB[y], ALVOS_RGB[x])

# ==============================================================================
# 7. DASHBOARD ESTILO OSRTT
# ==============================================================================
def criar_matriz_calor(ax, tipo):
    matriz = np.zeros((6, 6))
    textos = np.empty((6, 6), dtype=object)

    for i, origem in enumerate(ALVOS_RGB):
        for j, destino in enumerate(ALVOS_RGB):
            dados = DADOS_ENSAIO.get((origem, destino))
            if origem == destino:
                matriz[i, j] = 0
                textos[i, j] = "-"
            elif dados:
                val = dados['tempo_med'] if tipo == 'tempo' else dados['overshoot_med']
                matriz[i, j] = val
                marcador = "*" if dados.get('saturacao') else ""
                textos[i, j] = f"{val:.1f}{marcador}"
            else:
                matriz[i, j] = np.nan
                textos[i, j] = "Erro"

    cmap = plt.cm.RdYlGn_r
    vmax_lim = 15 if tipo == 'tempo' else 30
    im = ax.imshow(matriz, cmap=cmap, vmin=0, vmax=vmax_lim)

    for i in range(6):
        for j in range(6):
            cor = "black" if (not np.isnan(matriz[i, j]) and matriz[i, j] < (vmax_lim / 2)) else "white"
            ax.text(j, i, textos[i, j], ha="center", va="center", color=cor, fontweight='bold')

    ax.set_xticks(np.arange(6)); ax.set_yticks(np.arange(6))
    ax.set_xticklabels(ALVOS_RGB); ax.set_yticklabels(ALVOS_RGB)
    ax.set_xlabel("Para (Destino)"); ax.set_ylabel("De (Origem)")
    ax.set_title("Media G2G (ms)" if tipo == 'tempo' else "Media Overshoot (%)", fontweight='bold', pad=10)
    return im

def gerar_dashboard_osrtt():
    pasta_sessao = criar_pasta_sessao(METADADOS)
    caminho_resumo = exportar_resumo_csv(pasta_sessao)
    caminho_config = exportar_config_json(pasta_sessao)
    caminho_dados_brutos = None
    if METADADOS.get('exportar_dados_brutos'):
        caminho_dados_brutos = exportar_dados_brutos_csv(pasta_sessao)

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(14, 8))
    fig.canvas.manager.set_window_title(f"Relatorio Metrologico - {METADADOS['monitor']}")

    gs = GridSpec(3, 2, height_ratios=[4, 1, 1], figure=fig)
    ax_tempo = fig.add_subplot(gs[0, 0])
    ax_over = fig.add_subplot(gs[0, 1])

    criar_matriz_calor(ax_tempo, 'tempo')
    criar_matriz_calor(ax_over, 'overshoot')

    fig.canvas.mpl_connect('button_press_event', lambda event: on_click_matriz(event, ax_tempo, 'tempo'))
    fig.canvas.mpl_connect('button_press_event', lambda event: on_click_matriz(event, ax_over, 'overshoot'))

    tempos_validos = [d['tempo_med'] for (o, dst), d in DADOS_ENSAIO.items() if o != dst]
    over_validos = [d['overshoot_med'] for (o, dst), d in DADOS_ENSAIO.items() if o != dst]

    ax_stats = fig.add_subplot(gs[1, :]); ax_stats.axis('off')
    if tempos_validos:
        reps_ok = ESTATISTICAS.get('reps_totais_ok', 0)
        reps_tent = ESTATISTICAS.get('reps_totais_tentadas', 0)
        pct_validas = 100.0 * reps_ok / reps_tent if reps_tent else 0.0
        satur = ESTATISTICAS.get('transicoes_com_saturacao', 0)
        txt_stats = (
            f" ESTATISTICAS DO PAINEL\n"
            f" Media G2G: {np.mean(tempos_validos):.2f} ms   |   Pior Transicao: {np.max(tempos_validos):.2f} ms   |   Melhor: {np.min(tempos_validos):.2f} ms\n"
            f" Media Overshoot: {np.mean(over_validos):.1f}%   |   Pior Overshoot: {np.max(over_validos):.1f}%\n"
            f" Repeticoes validas: {reps_ok}/{reps_tent} ({pct_validas:.0f}%)   |   Transicoes com sinal saturado (*): {satur}"
        )
    else:
        txt_stats = "Sem dados."
    ax_stats.text(0.5, 0.5, txt_stats, ha='center', va='center', fontsize=12,
                  bbox=dict(facecolor='#222', edgecolor='#00ffcc', boxstyle='round,pad=1'))

    ax_meta = fig.add_subplot(gs[2, :]); ax_meta.axis('off')
    txt_meta = (
        f" METADADOS DO ENSAIO (Norma IDMS/VESA ClearMR)\n"
        f" Monitor: {METADADOS['monitor']}   |   Overdrive: {METADADOS['overdrive']}   |   Warm-up: {METADADOS['warmup']} min\n"
        f" Amostragem: {METADADOS['repeticoes']} ciclos   |   DAQ: ESP32 (taxa real medida por captura)   |   Corte Optico: 10-90% na Luminancia Linear\n"
        f" Resultados salvos em: {pasta_sessao}\n"
        f" (Dica: clique nas celulas para abrir os graficos brutos da transicao. * = sinal saturado no ADC)"
    )
    ax_meta.text(0.5, 0.5, txt_meta, ha='center', va='center', fontsize=10, color='gray')

    plt.tight_layout()

    caminho_png = os.path.join(pasta_sessao, 'dashboard.png')
    fig.savefig(caminho_png, dpi=200, facecolor=fig.get_facecolor())

    plt.show()

    resumo_arquivos = (
        f"Resultados salvos em:\n{pasta_sessao}\n\n"
        f"- {os.path.basename(caminho_resumo)}\n"
        f"- {os.path.basename(caminho_png)}\n"
        f"- {os.path.basename(caminho_config)}"
    )
    if caminho_dados_brutos:
        resumo_arquivos += f"\n- {os.path.basename(caminho_dados_brutos)}"
    messagebox.showinfo("Ensaio concluido", resumo_arquivos)

    iniciar_interface()

# ==============================================================================
# 8. TELA INICIAL (MENU INFINITO COM SAVE)
# ==============================================================================
def iniciar_interface():
    cfg = carregar_config_salva()

    root = tk.Tk()
    root.title("Configuracao de Ensaio Metrologico")
    root.geometry("460x680")
    root.eval('tk::PlaceWindow . center')

    ttk.Label(root, text="TCC - Analisador G2G", font=("Arial", 14, "bold")).pack(pady=10)
    frame = ttk.Frame(root); frame.pack(pady=5, padx=20, fill='x')

    ttk.Label(frame, text="Porta Serial:").grid(row=0, column=0, sticky='w', pady=5)
    porta_var = tk.StringVar(value=cfg.get('porta'))
    ttk.Entry(frame, textvariable=porta_var, width=15).grid(row=0, column=1, sticky='e')

    ttk.Label(frame, text="Nome do Monitor:").grid(row=1, column=0, sticky='w', pady=5)
    monitor_var = ttk.Combobox(frame, values=["LG ULTRAGEAR 24GS60F-B", "15,6 HQ LED 60Hz", "AOC LM522"], width=22)
    monitor_var.set(cfg.get('monitor')); monitor_var.grid(row=1, column=1, sticky='e')

    ttk.Label(frame, text="Overdrive:").grid(row=2, column=0, sticky='w', pady=5)
    overdrive_var = ttk.Combobox(frame, values=["Desligado", "Normal", "Fast", "Faster", "Extreme"], width=22)
    overdrive_var.set(cfg.get('overdrive')); overdrive_var.grid(row=2, column=1, sticky='e')

    ttk.Label(frame, text="Tempo Ligado (Minutos):").grid(row=3, column=0, sticky='w', pady=5)
    warmup_var = tk.StringVar(value=cfg.get('warmup'))
    ttk.Entry(frame, textvariable=warmup_var, width=15).grid(row=3, column=1, sticky='e')

    ttk.Label(frame, text="Repeticoes por Cor (>20):").grid(row=4, column=0, sticky='w', pady=5)
    rep_var = tk.StringVar(value=cfg.get('repeticoes'))
    ttk.Entry(frame, textvariable=rep_var, width=15).grid(row=4, column=1, sticky='e')

    ttk.Label(frame, text="Repouso (Segundos):").grid(row=5, column=0, sticky='w', pady=5)
    int_var = tk.StringVar(value=cfg.get('intervalo'))
    ttk.Entry(frame, textvariable=int_var, width=15).grid(row=5, column=1, sticky='e')

    ttk.Separator(frame, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky='ew', pady=10)

    ttk.Label(frame, text="Janela de Captura (ms):").grid(row=7, column=0, sticky='w', pady=5)
    janela_var = tk.StringVar(value=str(cfg.get('janela_captura_ms', JANELA_CAPTURA_MS_PADRAO)))
    ttk.Entry(frame, textvariable=janela_var, width=15).grid(row=7, column=1, sticky='e')

    mostrar_raw_var = tk.BooleanVar(value=bool(cfg.get('mostrar_raw', False)))
    ttk.Checkbutton(frame, text="Mostrar Curva Bruta (ADC) nos Graficos",
                    variable=mostrar_raw_var).grid(row=8, column=0, columnspan=2, sticky='w', pady=5)

    dados_brutos_var = tk.BooleanVar(value=bool(cfg.get('exportar_dados_brutos', False)))
    ttk.Checkbutton(frame, text="Exportar dados brutos (CSV grande)",
                    variable=dados_brutos_var).grid(row=9, column=0, columnspan=2, sticky='w', pady=5)

    # --- ESTIMATIVA DE TEMPO ---
    lbl_tempo_estimado = tk.Label(root, text="Calculando tempo...", font=("Arial", 10, "italic"), fg="#ff3399")
    lbl_tempo_estimado.pack(pady=8)

    def atualizar_tempo_estimado(*args):
        try:
            reps = int(rep_var.get())
            interv = float(int_var.get())
            janela_s = float(janela_var.get()) / 1000.0
            overhead_por_captura = janela_s + 0.3  # captura + transmissao + folga
            total_transicoes = len(ALVOS_RGB) ** 2
            tempo_total_segundos = total_transicoes * reps * (interv + overhead_por_captura)
            minutos = int(tempo_total_segundos // 60)
            segundos = int(tempo_total_segundos % 60)
            lbl_tempo_estimado.config(text=f"Tempo Estimado do Ensaio: ~ {minutos} min e {segundos} s")
        except ValueError:
            lbl_tempo_estimado.config(text="Tempo Estimado: digite valores validos!")

    rep_var.trace_add("write", atualizar_tempo_estimado)
    int_var.trace_add("write", atualizar_tempo_estimado)
    janela_var.trace_add("write", atualizar_tempo_estimado)
    atualizar_tempo_estimado()

    def on_start():
        config_atual = {
            'porta': normalizar_porta(porta_var.get()), 'monitor': monitor_var.get(),
            'overdrive': overdrive_var.get(), 'warmup': warmup_var.get(),
            'repeticoes': rep_var.get(), 'intervalo': int_var.get(),
            'janela_captura_ms': janela_var.get(),
            'exportar_dados_brutos': dados_brutos_var.get(),
            'mostrar_raw': mostrar_raw_var.get()
        }
        salvar_config(config_atual)
        root.destroy()
        executar_ensaio(config_atual)

    tk.Button(root, text="INICIAR AQUISICAO", font=("Arial", 11, "bold"), bg="#00ffcc",
              command=on_start, height=2).pack(pady=15, fill='x', padx=20)
    root.mainloop()

if __name__ == "__main__":
    iniciar_interface()
