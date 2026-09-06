"""
================================================================================
 TCC - ANALISADOR ÓPTICO DE DISPLAYS (TEMPO DE RESPOSTA G2G)
================================================================================
 Este script atua como o orquestrador do experimento. Ele se comunica com o
 microcontrolador (ESP32) via Serial, controla os estímulos visuais na tela
 e realiza o tratamento matemático dos dados utilizando os padrões da VESA.
================================================================================
"""

import serial
import time
import pygame
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import win32api # Biblioteca para ler informações de hardware do Windows

# ==============================================================================
# 1. CONFIGURAÇÕES GERAIS DO EXPERIMENTO
# ==============================================================================
PORTA_SERIAL = 'COM5'       # Lembre-se de alterar para a porta correta do lab (ex: COM4, COM7)
BAUD_RATE = 115200          # Velocidade de comunicação (deve ser igual no C++)
TEMPO_POR_AMOSTRA_MS = 0.1  # Resolução do timer de hardware do ESP32 (100 us = 0.1 ms)

# Níveis de cinza (8-bits) padronizados pela indústria para testes de monitores
ALVOS_RGB = [0, 51, 102, 153, 204, 255]

# ==============================================================================
# 2. VARIÁVEIS DE CALIBRAÇÃO METROLÓGICA (VESA E OVERSHOOT)
# ==============================================================================
# CORTE_VESA: Define a janela de tempo da transição.
# 0.10 = Mede de 10% a 90% da curva, ignorando ruídos elétricos na base e no topo
CORTE_VESA_PERC = 0.10 

# TOLERANCIA_OVERSHOOT: Limite mínimo para registrar um pico de Overdrive.
# 0.02 = Ignora picos menores que 2% acima do alvo (filtra ruídos térmicos).
TOLERANCIA_OVERSHOOT = 0.02 
# ==============================================================================

def obter_info_monitor():
    """ Lê a API do Windows para descobrir o nome do monitor e a taxa de Hz """
    try:
        device = win32api.EnumDisplayDevices(None, 0)
        monitor = win32api.EnumDisplayDevices(device.DeviceName, 0)
        nome = monitor.DeviceString if monitor.DeviceString else "Monitor Padrão"
        settings = win32api.EnumDisplaySettings(device.DeviceName, -1)
        return f"{nome} - {settings.DisplayFrequency}Hz"
    except:
        return "Display Desconhecido"

def main():
    print(f">>> Detectado: {obter_info_monitor()}")
    
    # --------------------------------------------------------------------------
    # INICIALIZAÇÃO DO HARDWARE (ESP32)
    # --------------------------------------------------------------------------
    print(f">>> Conectando na porta {PORTA_SERIAL}...")
    try:
        esp32 = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
        esp32.setDTR(False)
        esp32.setRTS(False)
        time.sleep(2) # Aguarda o boot da placa
        esp32.reset_input_buffer()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar: {e}")
        return

    # --------------------------------------------------------------------------
    # INICIALIZAÇÃO DA INTERFACE GRÁFICA
    # --------------------------------------------------------------------------
    pygame.init()
    tela = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    
    todas_leituras = []
    
    # ==========================================================================
    # LOOP DE TESTES (Executa a transição do Preto para cada alvo RGB)
    # ==========================================================================
    for rgb_alvo in ALVOS_RGB:
        print(f"\n--- Iniciando teste: Preto absoluto -> RGB {rgb_alvo} ---")
        
        # 1. Estabiliza os cristais líquidos na cor preta
        tela.fill((0, 0, 0))
        pygame.display.flip()
        time.sleep(1)

        # 2. Disparo Sincronizado: Envia o comando serial e pinta a tela no mesmo instante
        esp32.write(b'I') 
        tela.fill((rgb_alvo, rgb_alvo, rgb_alvo))
        pygame.display.flip()

        dados_brutos = []
        tempo_inicio = time.time()
        
        # 3. Leitura em alta velocidade do buffer serial
        while True:
            pygame.event.pump() # Mantém o processo do Pygame responsivo no Windows
            try:
                linha = esp32.readline().decode('utf-8', errors='ignore').strip()
                if linha == "FIM":
                    break
                elif linha.isdigit():
                    dados_brutos.append(int(linha))
            except:
                continue
                
            # Trava de segurança (Timeout)
            if time.time() - tempo_inicio > 4.0:
                print("[ERRO] Timeout na leitura serial.")
                break

        # ----------------------------------------------------------------------
        # PROCESSAMENTO MATEMÁTICO (Curva Gamma e Limites VESA)
        # ----------------------------------------------------------------------
        if len(dados_brutos) > 0:
            voltagens_adc = np.array(dados_brutos)
            
            # Isola os momentos de repouso para definir as referências
            v_min = np.mean(voltagens_adc[:200])
            v_target_raw = np.mean(voltagens_adc[-200:])
            v_max_raw = np.max(voltagens_adc)
            amplitude_raw = v_target_raw - v_min
            
            # Se for o teste 0 (Preto -> Preto), marca como linha de base
            if rgb_alvo == 0 or amplitude_raw < 20:
                todas_leituras.append({'valido': False, 'rgb_alvo': rgb_alvo, 'raw_array': voltagens_adc})
                continue
            
            # Conversão Não-Linear: Transforma a energia elétrica linear em escala RGB visual (Gamma 2.2)
            v_max_teorico = amplitude_raw / ((rgb_alvo / 255.0) ** 2.2)
            if v_max_teorico <= 0: v_max_teorico = 1

            voltagens_limpas = np.clip(voltagens_adc - v_min, 0.0001, None)
            escala_luminancia = np.clip(voltagens_limpas / v_max_teorico, 0, 1.5)
            rgb_array = 255.0 * (escala_luminancia ** (1/2.2))
            
            # Calcula os limites VESA dinamicamente sobre o sinal já convertido
            rgb_min = np.mean(rgb_array[:200])
            rgb_target = np.mean(rgb_array[-200:])
            rgb_amplitude = rgb_target - rgb_min
            
            limite_inferior = rgb_min + (rgb_amplitude * CORTE_VESA_PERC)
            limite_superior = rgb_min + (rgb_amplitude * (1.0 - CORTE_VESA_PERC))

            # Procura o ponto exato onde a curva rompe a barreira dos limites
            indice_inf = np.argmax(rgb_array >= limite_inferior)
            indice_sup = np.argmax(rgb_array >= limite_superior)
            
            # Calcula o tempo total em milissegundos
            tempo_resposta = (indice_sup - indice_inf) * TEMPO_POR_AMOSTRA_MS
            
            # Calcula a porcentagem do pico que ultrapassou o alvo (Overdrive)
            overshoot_taxa = (v_max_raw - v_target_raw) / amplitude_raw
            overshoot_perc = (overshoot_taxa * 100) if overshoot_taxa >= TOLERANCIA_OVERSHOOT else 0
            
            # Armazena tudo em um dicionário para enviar ao gerador de gráficos
            todas_leituras.append({
                'valido': True, 'rgb_alvo': rgb_alvo, 'rgb_array': rgb_array, 
                'raw_array': voltagens_adc, 'tempo': tempo_resposta, 'overshoot': overshoot_perc,
                'lim_inf': limite_inferior, 'lim_sup': limite_superior, 'rgb_target': rgb_target
            })
            print(f"> Resultado: Tempo {tempo_resposta:.2f} ms | Overshoot {overshoot_perc:.1f}%")

    pygame.quit()
    esp32.close()
    
    # Chama a função de plotagem apenas se houver dados válidos
    gerar_grafico(todas_leituras, obter_info_monitor())

# ==============================================================================
# GERAÇÃO DO PAINEL GRÁFICO (Matplotlib)
# ==============================================================================
def gerar_grafico(todas_leituras, info_painel):
    if not todas_leituras: return

    plt.style.use('dark_background')
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle(f'Escala de Cinza (0-255) | {info_painel}\nMedição G2G Automática (VESA {CORTE_VESA_PERC*100:.0f}%)', fontsize=16, fontweight='bold')
    axes = axes.flatten()

    for i, leitura in enumerate(todas_leituras):
        if i >= 6: break 
        ax = axes[i]
        tempos = np.arange(len(leitura['raw_array'])) * TEMPO_POR_AMOSTRA_MS
        
        # Plotagem exclusiva da linha de base (Preto Absoluto)
        if not leitura['valido']:
            ax.plot(tempos, leitura['raw_array'], color='#555555')
            ax.set_title(f'RGB {leitura["rgb_alvo"]} (Base de Ruído)', color='#aaaaaa')
            ax.set_ylim(-10, 270)
            ax.set_yticks(ALVOS_RGB)
            ax.grid(True, alpha=0.1)
            continue
            
        # Plotagem principal: A Curva RGB e as retas horizontais VESA
        ax.plot(tempos, leitura['rgb_array'], color='#00ffcc', zorder=3)
        ax.axhline(leitura['lim_inf'], color='red', linestyle='--', alpha=0.5, zorder=2)
        ax.axhline(leitura['lim_sup'], color='red', linestyle='--', alpha=0.5, zorder=2)
        ax.axhline(leitura['rgb_target'], color='#ccff00', alpha=0.4, zorder=2)
        
        # Sombreamento visual demonstrando o tempo percorrido
        idx_inf = np.argmax(leitura['rgb_array'] >= leitura['lim_inf'])
        idx_sup = np.argmax(leitura['rgb_array'] >= leitura['lim_sup'])
        ax.axvspan(tempos[idx_inf], tempos[idx_sup], color='red', alpha=0.2, zorder=1)
        
        # Títulos e formatação fixa do eixo Y primário (Sem Auto-Zoom)
        ax.set_title(f'RGB {leitura["rgb_alvo"]} | {leitura["tempo"]:.2f}ms | OS: {leitura["overshoot"]:.1f}%')
        ax.set_ylim(-10, 270)
        ax.set_yticks(ALVOS_RGB)
        ax.grid(True, alpha=0.2)
        
        # Adiciona os rótulos de eixo (Apenas nas bordas externas para não poluir)
        if i % 3 == 0: ax.set_ylabel('Sinal Convertido (RGB)')
        if i >= 3: ax.set_xlabel('Tempo (ms)')
        
        # Eixo Secundário: Tensão Bruta (Bits ADC) exibido como plano de fundo
        ax2 = ax.twinx()
        ax2.plot(tempos, leitura['raw_array'], color='#ff3399', alpha=0.35, zorder=0)
        ax2.set_ylim(0, 4095)
        
        # Rótulos do eixo secundário (Apenas na borda direita)
        if i % 3 == 2:
            ax2.set_ylabel('Tensão Bruta (Bits ADC)', color='#ff3399', alpha=0.8)
        else:
            ax2.set_yticklabels([])

    plt.tight_layout()
    plt.subplots_adjust(top=0.88) # Espaço extra para o título principal
    plt.show()

if __name__ == "__main__":
    main()