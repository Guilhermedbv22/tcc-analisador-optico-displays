"""Auditoria offline do analisador original. Não abre serial nem interface gráfica.

Uso: python auditar.py --entrada /pasta/com/analisador.py/e/csvs --saida resultados
Dependências: numpy, pandas, scipy, matplotlib. Python >= 3.10.
Executa funções extraídas por AST do arquivo fornecido, sem reescrevê-las.
Os testes documentam falhas encontradas; a saída zero indica conclusão da auditoria,
não aprovação metrológica do instrumento. Os arquivos originais não são alterados.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def carregar_nucleo(arquivo):
    fonte = arquivo.read_text(encoding='utf-8-sig')
    compile(fonte, str(arquivo), 'exec')  # sintaxe de todo o arquivo
    arvore = ast.parse(fonte)
    nomes = {'verificar_saturacao', 'processar_curva', 'capturar_transicao',
             'capturar_transicao_valida', 'configurar_janela_captura'}
    contexto = {'np': np}
    funcoes = []
    for no in arvore.body:
        if isinstance(no, ast.Assign):
            try:
                valor = ast.literal_eval(no.value)
            except (ValueError, TypeError):
                continue
            for alvo in no.targets:
                if isinstance(alvo, ast.Name):
                    contexto[alvo.id] = valor
        elif isinstance(no, ast.FunctionDef) and no.name in nomes:
            funcoes.append(no)
    exec(compile(ast.Module(body=funcoes, type_ignores=[]), str(arquivo), 'exec'), contexto)
    return contexto


def ler_csv(arquivo):
    cabecalho = arquivo.open(encoding='utf-8-sig').readline()
    return pd.read_csv(arquivo, sep=';' if ';' in cabecalho else ',')


def auditar_dados(entrada, saida, nucleo):
    dados = ler_csv(entrada / 'dados_brutos.csv')
    resumo = ler_csv(entrada / 'resumo.csv')
    linhas, curvas = [], {}
    for (o, d, rep), grupo in dados.groupby(['origem_rgb', 'destino_rgb', 'repeticao']):
        grupo = grupo.sort_values('indice_amostra')
        indices = grupo.indice_amostra.to_numpy()
        assert np.array_equal(indices, np.arange(len(indices))), 'Índices ausentes/duplicados'
        bruto = grupo.adc_bruto.to_numpy(float)
        # O CSV contém tempos sintetizados e arredondados a 0,001 ms, não timestamps.
        dt = float(np.polyfit(indices, grupo.tempo_ms, 1)[0])
        g2g, ov, det = nucleo['processar_curva'](bruto, o, d, dt)
        ref = resumo[(resumo.origem_rgb == o) & (resumo.destino_rgb == d)].iloc[0]
        linha = dict(origem=int(o), destino=int(d), repeticao=int(rep), n=len(bruto),
                     dt_estimado_ms=dt, taxa_media_inferida_sps=1000/dt,
                     inicio_adc=float(bruto[:50].mean()), fim_adc=float(bruto[-50:].mean()),
                     ruido_inicio_dp_adc=float(bruto[:50].std(ddof=1)),
                     ruido_fim_dp_adc=float(bruto[-50:].std(ddof=1)),
                     minimo_adc=float(bruto.min()), maximo_adc=float(bruto.max()),
                     g2g_reproduzido_ms=float(g2g), overshoot_reproduzido_pct=float(ov),
                     delta_resumo_g2g_ms=float(g2g-ref.g2g_ms),
                     delta_resumo_overshoot_pct=float(ov-ref.overshoot_pct),
                     saturado=bool(det['saturado']))
        linha['amplitude_adc'] = linha['fim_adc']-linha['inicio_adc']
        linha['amplitude_div_ruido'] = abs(linha['amplitude_adc']) / max(linha['ruido_inicio_dp_adc'], linha['ruido_fim_dp_adc'])
        for janela in [3, 5, 11, 21]:
            suavizado = uniform_filter1d(bruto, size=janela, mode='nearest')
            t_fil, ov_fil, _ = nucleo['processar_curva'](suavizado, o, d, dt)
            linha[f'diagnostico_media_{janela}_g2g_ms'] = float(t_fil)
            linha[f'diagnostico_media_{janela}_overshoot_pct'] = float(ov_fil)
        linhas.append(linha)
        curvas[(o, d)] = (indices*dt, bruto, det)
    analise = pd.DataFrame(linhas)
    analise.to_csv(saida / 'recalculo_e_sensibilidade.csv', index=False)
    reais = analise[analise.origem != analise.destino]
    estat = dict(amostras=len(dados), capturas=len(analise), transicoes_reais=len(reais),
                 adc_min=int(dados.adc_bruto.min()), adc_max=int(dados.adc_bruto.max()),
                 g2g_media_ms=float(reais.g2g_reproduzido_ms.mean()),
                 overshoot_media_pct=float(reais.overshoot_reproduzido_pct.mean()),
                 taxa_media_min_sps=float(analise.taxa_media_inferida_sps.min()),
                 taxa_media_max_sps=float(analise.taxa_media_inferida_sps.max()),
                 maior_erro_replay_g2g_ms=float(analise.delta_resumo_g2g_ms.abs().max()),
                 maior_erro_replay_overshoot_pct=float(analise.delta_resumo_overshoot_pct.abs().max()))
    return analise, curvas, estat


def testes_sinais(nucleo):
    t = np.arange(1000)*0.1
    def exponencial(amplitude=1000, inicio=30, tau=5, offset=500):
        return offset + amplitude*(1-np.exp(-np.maximum(t-inicio, 0)/tau))
    ideal = 5*np.log(9)
    casos = [
        ('exponencial_subida', exponencial(), 0, 255, ideal, 'erro <= 0,15 ms'),
        ('exponencial_descida', exponencial(-1000, offset=1700), 255, 0, ideal, 'erro <= 0,15 ms'),
        ('degrau_pequeno_20_contagens', exponencial(20), 0, 51, ideal, 'medir ou invalidar; nunca 0 ms válido'),
        ('sem_transicao', np.full(1000, 500.), 0, 255, None, 'invalidar transição ausente'),
        ('pre_trigger_contaminado', 500+1000*np.clip((t-.5)/20,0,1), 0, 255, 16., 'detectar patamar inicial contaminado; rampa de 20 ms'),
        ('fim_nao_estabilizado', exponencial(inicio=85, tau=10), 0, 255, 10*np.log(9), 'invalidar janela incompleta'),
        ('clipping_analogico_2400', np.minimum(exponencial(3000), 2400), 0, 255, ideal, 'sinalizar clipping analógico conhecido no teste'),
    ]
    spike = exponencial(); spike[100] = 1700
    casos.append(('pico_isolado_antes_transicao', spike, 0, 255, ideal, 'não confundir pico de uma amostra com transição'))
    clip = exponencial(); clip[420] = 4095
    casos.append(('uma_amostra_em_4095', clip, 0, 255, ideal, 'sinalizar pico recortado para overshoot'))
    saida=[]
    for nome, sinal, o, d, esperado, criterio in casos:
        medido, ov, det = nucleo['processar_curva'](sinal, o, d, .1)
        if nome in ('exponencial_subida','exponencial_descida'):
            resultado='OK' if abs(medido-esperado)<=.15 else 'FALHA'
        elif nome in ('clipping_analogico_2400','uma_amostra_em_4095'):
            resultado='LIMITACAO/FALHA' if not det['saturado'] else 'DETECTADO'
        else:
            resultado='FALHA: retorna métrica sem invalidar'
        saida.append(dict(caso=nome, esperado_ms=esperado, medido_ms=float(medido),
                          overshoot_pct=float(ov), saturado=bool(det['saturado']),
                          criterio=criterio, resultado=resultado))
    return pd.DataFrame(saida)


def monte_carlo(nucleo):
    rng = np.random.default_rng(20260906)
    t = np.arange(1000)*.1
    sinal = 450 + 70*(1-np.exp(-np.maximum(t-30,0)/5))
    medidos = np.array([nucleo['processar_curva'](sinal+rng.normal(0,12,1000),0,51,.1)[:2]
                       for _ in range(1000)])
    return dict(repeticoes=1000, seed=20260906, amplitude_adc=70, ruido_dp_adc=12,
                g2g_verdadeiro_ms=float(5*np.log(9)), overshoot_verdadeiro_pct=0,
                g2g_mediana_ms=float(np.median(medidos[:,0])),
                g2g_p05_p95_ms=np.percentile(medidos[:,0],[5,95]).tolist(),
                overshoot_mediana_pct=float(np.median(medidos[:,1])),
                overshoot_p05_p95_pct=np.percentile(medidos[:,1],[5,95]).tolist())


class RelogioSimulado:
    def __init__(self): self.valor = 0.
    def time(self): self.valor += .001; return self.valor
    def sleep(self, duracao): self.valor += max(duracao, 0)


class SerialSimulada:
    def __init__(self, linhas): self.linhas = iter(linhas)
    def reset_input_buffer(self): pass
    def write(self, _): pass
    def readline(self): return next(self.linhas, b'')


def testes_protocolo(nucleo):
    resultados=[]
    tela=SimpleNamespace(fill=lambda _: None)
    for nome, n, duracao, valor, fim in [
        ('pacote_normal',1000,100000,500,True),
        ('pacote_sem_FIM',1000,100000,500,False),
        ('ADC_fora_de_faixa',1000,100000,5000,True),
        ('duracao_negativa',1000,-100000,500,True),
        ('janela_20ms_oferecida_pelo_firmware',200,20000,500,True),
    ]:
        relogio=RelogioSimulado()
        nucleo['time']=relogio
        nucleo['pygame']=SimpleNamespace(display=SimpleNamespace(flip=lambda:None), event=SimpleNamespace(pump=lambda:None))
        linhas=[f'META:{duracao},{n}\n'.encode()]+[f'{valor}\n'.encode()]*n
        if fim: linhas.append(b'FIM\n')
        serial=SerialSimulada(linhas)
        dados, dt=nucleo['capturar_transicao_valida'](serial,tela,0,255,0.5)
        resultados.append(dict(caso=nome,aceito=dados is not None,dt_ms=dt,
                                observacao='Validação de transporte, sem hardware'))
    return pd.DataFrame(resultados)


def graficos(saida, curvas, analise):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig, axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for ax,par in zip(axs.flat,[(0,51),(51,0),(0,255),(255,153)]):
        tempo,bruto,det=curvas[par]
        rec=analise[(analise.origem==par[0])&(analise.destino==par[1])].iloc[0]
        ax.plot(tempo,bruto,color='#1c7293',lw=.8,label='ADC bruto')
        ax.axhline(rec.inicio_adc,color='#595959',ls=':',label='Média inicial/final')
        ax.axhline(rec.fim_adc,color='#595959',ls=':')
        for fra in [.1,.9]: ax.axhline(rec.inicio_adc+fra*rec.amplitude_adc,color='#bc5800',ls='--',alpha=.7)
        ax.axvspan(det['t_inf'],det['t_sup'],color='#f1ab56',alpha=.25,label='Intervalo escolhido pelo código')
        ax.set(title=f'{par[0]} → {par[1]} | {rec.g2g_reproduzido_ms:.2f} ms | {rec.overshoot_reproduzido_pct:.1f}%',
               xlabel='Tempo reconstruído no CSV (ms)',ylabel='Contagens ADC')
        ax.grid(alpha=.15)
    axs[0,0].legend(fontsize=8,loc='lower right')
    fig.suptitle('Auditoria dos dados reais: o ruído e os patamares precisam ser validados',fontsize=15)
    fig.savefig(saida/'diagnostico_curvas.png',dpi=170)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    for d in [0,51,102,153,204,255]:
        rec=analise[analise.destino==d]
        ax.plot(rec.origem,rec.fim_adc,'o-',label=f'Destino {d}')
    ax.set(xlabel='Nível RGB de origem',ylabel='Média das últimas 50 amostras (ADC)',
           title='Mesmo destino, patamares diferentes entre capturas')
    ax.legend(ncol=3,fontsize=8);ax.grid(alpha=.2)
    fig.savefig(saida/'patamares_por_destino.png',dpi=170);plt.close(fig)
    tempo,bruto,det=curvas[(0,51)]
    rec=analise[(analise.origem==0)&(analise.destino==51)].iloc[0]
    fig,ax=plt.subplots(figsize=(11,4.8),layout='constrained')
    ax.plot(tempo,bruto,color='#1c7293',lw=.8)
    for fracao,nome in [(.1,'10%'),(.9,'90%')]:
        valor=rec.inicio_adc+fracao*rec.amplitude_adc
        ax.axhline(valor,color='#bc5800',ls='--',lw=1.4)
        ax.text(98,valor+2,f'{nome}: {valor:.2f}',ha='right',color='#8f4300',
                bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':1})
    ax.axvspan(det['t_inf'],det['t_sup'],color='#f1ab56',alpha=.4)
    ax.annotate('Pico isolado escolhido como 90%\n555 contagens, em 38,29 ms',
                xy=(tempo[383],bruto[383]),xytext=(3,582),fontsize=10,
                arrowprops={'arrowstyle':'->','color':'#8f4300'})
    ax.text(61,461,'G2G retornado: 1,20 ms\nO sinal ainda estava subindo.',fontsize=11,
            bbox={'facecolor':'#fff4e6','edgecolor':'#e7b375','boxstyle':'round,pad=.5'})
    ax.set(xlabel='Tempo reconstruído no CSV (ms)',ylabel='Contagens ADC',
           title='Transição real 0 → 51: um pico de ruído encerra a medição cedo demais',ylim=(440,605))
    ax.grid(alpha=.15)
    fig.savefig(saida/'diagnostico_0_51.png',dpi=170);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entrada',type=Path,required=True)
    parser.add_argument('--saida',type=Path,default=Path('resultados_auditoria'))
    args=parser.parse_args();args.saida.mkdir(parents=True,exist_ok=True)
    nucleo=carregar_nucleo(args.entrada/'analisador.py')
    analise,curvas,estat=auditar_dados(args.entrada,args.saida,nucleo)
    testes_sinais(nucleo).to_csv(args.saida/'testes_sinais.csv',index=False)
    estat['monte_carlo']=monte_carlo(nucleo)
    testes_protocolo(nucleo).to_csv(args.saida/'testes_protocolo.csv',index=False)
    estat['sha256_entradas']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.entrada.iterdir() if p.suffix in ('.py','.ino','.csv','.json')}
    (args.saida/'estatisticas.json').write_text(json.dumps(estat,indent=2,ensure_ascii=False)+'\n')
    graficos(args.saida,curvas,analise)
    print(json.dumps(estat,indent=2,ensure_ascii=False))


if __name__=='__main__': main()
