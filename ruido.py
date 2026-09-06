"""
Script de Diagnóstico de Ruído e Estabilidade Analógica
Exporta os dados brutos para análise em planilhas.
"""
import serial
import time
import pygame
import numpy as np
import matplotlib.pyplot as plt
import csv

# --- Parâmetros de Configuração ---
PORTA_SERIAL = 'COM5'
BAUD_RATE = 115200
COR_ESTATICA = (128, 128, 128) # Cor fixa para avaliação

def diagnostico():
    print(f"Conectando ao ESP32 na porta {PORTA_SERIAL}...")
    try:
        esp32 = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
        esp32.setDTR(False)
        esp32.setRTS(False)
        time.sleep(2) 
        esp32.reset_input_buffer() 
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return

    # Inicia tela cheia para emissão constante de luz
    pygame.init()
    tela = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    tela.fill(COR_ESTATICA)
    pygame.display.flip()
    
    # Aguarda o sensor e a tela estabilizarem
    time.sleep(2)
    
    print("Iniciando captura do sinal analógico...")
    esp32.write(b'I') 

    dados_brutos = []
    tempo_inicio = time.time()
    
    # Captura os dados do ADC
    while True:
        pygame.event.pump() 
        try:
            linha = esp32.readline().decode('utf-8', errors='ignore').strip()
            if linha == "FIM": break
            elif linha.isdigit(): dados_brutos.append(int(linha))
        except:
            continue
            
        if time.time() - tempo_inicio > 4.0:
            break

    pygame.quit()
    esp32.close()

    # Processamento e exportação dos dados
    if len(dados_brutos) > 0:
        voltagens_adc = np.array(dados_brutos)
        voltagens_v = voltagens_adc * (3.3 / 4095.0) # Conversão Bits para Volts
        tempos_ms = np.arange(len(voltagens_v)) * 0.1
        
        # Exporta dados para CSV (Formato legível pelo Excel em português)
        nome_arquivo = "diagnostico_ruido.csv"
        with open(nome_arquivo, mode='w', newline='') as arquivo_csv:
            escritor = csv.writer(arquivo_csv, delimiter=';')
            escritor.writerow(['Tempo (ms)', 'Bits (ADC)', 'Tensao (V)'])
            for i in range(len(dados_brutos)):
                v_fmt = str(round(voltagens_v[i], 4)).replace('.', ',')
                t_fmt = str(round(tempos_ms[i], 2)).replace('.', ',')
                escritor.writerow([t_fmt, voltagens_adc[i], v_fmt])
        print(f"Dados exportados para {nome_arquivo}")

        # Cálculos de ruído pico-a-pico
        media_v = np.mean(voltagens_v)
        print(f"\nResumo: Média {media_v:.4f}V | Variação de {np.max(voltagens_v) - np.min(voltagens_v):.4f}V")

        # Exibição Gráfica do Ruído
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(tempos_ms, voltagens_v, color='#ff3399', linewidth=1)
        ax.axhline(media_v, color='#00ffcc', linestyle='--', linewidth=2, label=f'Tensão Média: {media_v:.4f} V')
        
        ax.set_title(f'Diagnóstico de Ruído Elétrico (RGB {COR_ESTATICA})', fontweight='bold')
        ax.set_xlabel('Tempo (ms)')
        ax.set_ylabel('Tensão Lida (V)')
        ax.set_ylim(np.min(voltagens_v) - 0.05, np.max(voltagens_v) + 0.05) # Zoom inteligente no eixo Y
        
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    diagnostico()