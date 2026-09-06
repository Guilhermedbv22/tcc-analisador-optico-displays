"""
Script de Medição G2G (Tempo de Resposta) e Overshoot
"""
import serial
import time
import pygame
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import win32api

# --- Parâmetros de Configuração ---
PORTA_SERIAL = 'COM5'
BAUD_RATE = 115200
TEMPO_POR_AMOSTRA_MS = 0.1  # Resolução do timer do ESP32 (100us)
ALVOS_RGB = [0, 51, 102, 153, 204, 255] # Níveis de cinza padrão OSRTT
CORTE_VESA_PERC = 0.10      # Limites de medição (10% e 90%)
TOLERANCIA_OVERSHOOT = 0.02 # Ignora picos menores que 2% do alvo

def obter_info_monitor():
    """Lê as informações de hardware do monitor via API do Windows."""
    try:
        device = win32api.EnumDisplayDevices(None, 0)
        monitor = win32api.EnumDisplayDevices(device.DeviceName, 0)
        nome = monitor.DeviceString if monitor.DeviceString else "Monitor Padrão"
        settings = win32api.EnumDisplaySettings(device.DeviceName, -1)
        return f"{nome} - {settings.DisplayFrequency}Hz"
    except:
        return "Display Desconhecido"

def main():
    print(f"Detectado: {obter_info_monitor()}")
    
    # Inicializa conexão Serial com o hardware
    esp32 = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    esp32.setDTR(False)
    esp32.setRTS(False)
    time.sleep(2)
    esp32.reset_input_buffer()

    # Inicializa interface gráfica (Tela de Estímulo)
    pygame.init()
    tela = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    
    todas_leituras = []
    
    # Loop de testes para cada nível de cinza
    for rgb_alvo in ALVOS_RGB:
        print(f"\nTestando transição: Preto -> RGB {rgb_alvo}")
        
        # Estabiliza o painel no preto absoluto
        tela.fill((0, 0, 0))
        pygame.display.flip()
        time.sleep(1)

        # Dispara sincronizadamente o estímulo e o timer do ESP32
        esp32.write(b'I') 
        tela.fill((rgb_alvo, rgb_alvo, rgb_alvo))
        pygame.display.flip()

        dados_brutos = []
        tempo_inicio = time.time()
        
        # Recebe os dados da porta serial
        while True:
            pygame.event.pump() 
            try:
                linha = esp32.readline().decode('utf-8', errors='ignore').strip()
                if linha == "FIM":
                    break
                elif linha.isdigit():
                    dados_brutos.append(int(linha))
            except:
                continue
                
            if time.time() - tempo_inicio > 4.0:
                print("Erro: Timeout na leitura serial.")
                break

        # Processamento matemático dos dados
        if len(dados_brutos) > 0:
            voltagens_adc = np.array(dados_brutos)
            
            # Isola as médias de início e fim da transição
            v_min = np.mean(voltagens_adc[:200])
            v_target_raw = np.mean(voltagens_adc[-200:])
            v_max_raw = np.max(voltagens_adc)
            amplitude_raw = v_target_raw - v_min
            
            # Ignora testes sem emissão de luz (Preto para Preto)
            if rgb_alvo == 0 or amplitude_raw < 20:
                todas_leituras.append({'valido': False, 'rgb_alvo': rgb_alvo, 'raw_array': voltagens_adc})
                continue
            
            # Conversão Não-Linear (Curva Gamma 2.2) para escala de cor (0-255)
            v_max_teorico = amplitude_raw / ((rgb_alvo / 255.0) ** 2.2)
            if v_max_teorico <= 0: v_max_teorico = 1

            voltagens_limpas = np.clip(voltagens_adc - v_min, 0.0001, None)
            escala_luminancia = np.clip(voltagens_limpas / v_max_teorico, 0, 1.5)
            rgb_array = 255.0 * (escala_luminancia ** (1/2.2))
            
            # Calcula limites VESA (10% e 90%) na curva convertida
            rgb_min = np.mean(rgb_array[:200])
            rgb_target = np.mean(rgb_array[-200:])
            rgb_amplitude = rgb_target - rgb_min
            
            limite_inferior = rgb_min + (rgb_amplitude * CORTE_VESA_PERC)
            limite_superior = rgb_min + (rgb_amplitude * (1.0 - CORTE_VESA_PERC))

            # Encontra os índices de cruzamento para calcular o tempo
            indice_inf = np.argmax(rgb_array >= limite_inferior)
            indice_sup = np.argmax(rgb_array >= limite_superior)
            tempo_resposta = (indice_sup - indice_inf) * TEMPO_POR_AMOSTRA_MS
            
            # Cálculo de Overshoot elétrico
            overshoot_taxa = (v_max_raw - v_target_raw) / amplitude_raw
            overshoot_perc = (overshoot_taxa * 100) if overshoot_taxa >= TOLERANCIA_OVERSHOOT else 0
            
            todas_leituras.append({
                'valido': True, 'rgb_alvo': rgb_alvo, 'rgb_array': rgb_array, 
                'raw_array': voltagens_adc, 'tempo': tempo_resposta, 'overshoot': overshoot_perc,
                'lim_inf': limite_inferior, 'lim_sup': limite_superior, 'rgb_target': rgb_target
            })
            print(f"Resultado: Tempo {tempo_resposta:.2f} ms | Overshoot {overshoot_perc:.1f}%")

    pygame.quit()
    esp32.close()
    
    # Gera o Mosaico Gráfico Final usando Matplotlib
    gerar_grafico(todas_leituras, obter_info_monitor())

def gerar_grafico(todas_leituras, info_painel):
    """Função auxiliar para plotagem dos resultados na tela."""
    if not todas_leituras: return

    plt.style.use('dark_background')
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle(f'Escala de Cinza (0-255) | {info_painel}\nMedição G2G Automática (VESA 10-90%)', fontsize=16, fontweight='bold')
    axes = axes.flatten()

    for i, leitura in enumerate(todas_leituras):
        if i >= 6: break 
        ax = axes[i]
        tempos = np.arange(len(leitura['raw_array'])) * TEMPO_POR_AMOSTRA_MS
        
        if not leitura['valido']:
            ax.plot(tempos, leitura['raw_array'], color='#555555')
            ax.set_title(f'RGB {leitura["rgb_alvo"]} (Base)', color='#aaaaaa')
            continue
            
        # Curvas principais
        ax.plot(tempos, leitura['rgb_array'], color='#00ffcc')
        ax.axhline(leitura['lim_inf'], color='red', linestyle='--', alpha=0.5)
        ax.axhline(leitura['lim_sup'], color='red', linestyle='--', alpha=0.5)
        ax.axhline(leitura['rgb_target'], color='#ccff00', alpha=0.4)
        
        # Sombreamento do intervalo de resposta
        idx_inf = np.argmax(leitura['rgb_array'] >= leitura['lim_inf'])
        idx_sup = np.argmax(leitura['rgb_array'] >= leitura['lim_sup'])
        ax.axvspan(tempos[idx_inf], tempos[idx_sup], color='red', alpha=0.2)
        
        ax.set_title(f'RGB {leitura["rgb_alvo"]} | {leitura["tempo"]:.2f}ms | OS: {leitura["overshoot"]:.1f}%')
        
        # Eixo secundário (Tensão Bruta)
        ax2 = ax.twinx()
        ax2.plot(tempos, leitura['raw_array'], color='#ff3399', alpha=0.35)
        ax2.set_ylim(0, 4095)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()