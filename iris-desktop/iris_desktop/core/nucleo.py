"""Analise reproduzivel em contagens do ADC e resposta relativa, sem gamma suposto.
Os criterios abaixo sao escolhas documentadas do projeto, nao certificacao VESA.
"""
from dataclasses import dataclass, asdict
import numpy as np
from scipy.ndimage import median_filter

VERSAO_ANALISE = '4.1.0'


@dataclass
class Criterios:
    patamar_inicial_ms: float = 30.0
    patamar_final_ms: float = 40.0
    mediana_amostras: int = 3
    persistencia_ms: float = 0.3
    snr_minimo: float = 20.0
    amplitude_minima: float = 4.0
    tolerancia_acomodacao: float = 0.05
    permanencia_final_ms: float = 20.0
    limite_analogico_baixo: float | None = None
    limite_analogico_alto: float | None = None


def dispersao(x):
    """Conservadora: usa tambem desvio padrao, para nao esconder impulsos/PWM."""
    x = np.asarray(x, float)
    return float(max(np.std(x,ddof=1),1.4826*np.median(abs(x-np.median(x))),0.5))


def estatisticas(cap):
    x = np.asarray(cap.adc,float)
    dt = np.diff(np.asarray(cap.t_us,float))
    d = dict(n=len(x), media=float(x.mean()), mediana=float(np.median(x)),
             desvio_padrao=float(x.std(ddof=1)), sigma_robusto=float(1.4826*np.median(abs(x-np.median(x)))),
             minimo=float(x.min()), maximo=float(x.max()), pico_a_pico=float(np.ptp(x)),
             p01=float(np.percentile(x,1)),p99=float(np.percentile(x,99)),
             codigos_distintos=int(len(np.unique(x))),
             fracao_rail=float(np.mean((x<=2)|(x>=4093))))
    if len(dt) and np.all(dt>0):
        d.update(taxa_media_sps=float(1e6/dt.mean()), dt_mediano_us=float(np.median(dt)),
                 dt_p01_us=float(np.percentile(dt,1)),dt_p99_us=float(np.percentile(dt,99)),
                 dt_max_us=float(dt.max()), jitter_std_us=float(dt.std()),
                 leitura_p99_us=float(np.percentile(cap.leitura_us,99)))
    problemas = []
    nominal = cap.meta.get('period_us')
    if cap.meta.get('legacy') or nominal is None:
        problemas.append('temporizacao_nao_verificada')
    elif (cap.meta.get('missed', 0) > 0 or len(dt) == 0 or np.any(dt <= 0) or
          np.any(dt > 1.5 * nominal) or np.any(dt < .5 * nominal) or
          abs(np.mean(dt) - nominal) > .05 * nominal):
        problemas.append('temporizacao_irregular')
    if nominal is not None and np.any(cap.leitura_us >= nominal):
        problemas.append('conversao_longa')
    d.update(temporizacao_valida=not problemas, motivos_temporizacao=problemas)
    return d


def cruzamento(t, p, nivel, depois_ms, persistencia_ms):
    """Primeiro cruzamento interpolado que permanece acima pelo tempo pedido.
    A persistencia confirma o evento; nao e somada ao instante de cruzamento.
    """
    candidatos = np.flatnonzero((p[:-1]<nivel)&(p[1:]>=nivel))+1
    for i in candidatos:
        if t[i]<depois_ms:
            continue
        fim = np.searchsorted(t,t[i]+persistencia_ms,side='left')
        if fim >= len(p) or not np.all(p[i:fim+1]>=nivel):
            continue
        f = (nivel-p[i-1])/(p[i]-p[i-1])
        return float(t[i-1]+f*(t[i]-t[i-1]))
    return None


def analisar(cap, origem, destino, criterios=None, referencia=None):
    c = criterios or Criterios()
    if type(c.mediana_amostras) is not int or not 1 <= c.mediana_amostras <= 51 or c.mediana_amostras % 2 != 1 or c.persistencia_ms<0:
        raise ValueError('Filtro deve ser impar, 1..51 amostras; persistencia nao negativa.')
    if not 0<c.tolerancia_acomodacao<0.5 or c.snr_minimo<=0:
        raise ValueError('Criterios invalidos.')
    r = dict(versao=VERSAO_ANALISE,origem_rgb=int(origem),destino_rgb=int(destino),
             status='INVALIDA',valida=False,motivos=[],avisos=[],criterios=asdict(c),
             g2g_ms=None,t10_ms=None,t90_ms=None,acomodacao_ms=None,
             acomodacao_status='NAO_AVALIADA',overshoot_pct=None,overshoot_bruto_pct=None,
             overshoot_detectado=None,excursao_oposta_pct=None)
    t = np.asarray(cap.t_us,float)/1000
    y = np.asarray(cap.adc,float)
    if len(y)<200 or len(y)!=len(t) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(t)):
        r['motivos'].append('dados_insuficientes_ou_nao_finitos');return r
    if np.any(np.diff(t)<=0) or np.any((y<0)|(y>4095)):
        r['motivos'].append('tempo_ou_adc_invalido');return r
    t = t-t[0]
    r['estatisticas']=estatisticas(cap)
    if origem==destino:
        r.update(status='ESTATICA',motivos=['sem_transicao_solicitada'])
        return r
    ini = y[t<c.patamar_inicial_ms]
    final = y[t>=t[-1]-c.patamar_final_ms]
    if len(ini)<10 or len(final)<10 or t[-1] < c.patamar_inicial_ms+c.patamar_final_ms+5:
        r['motivos'].append('janela_insuficiente');return r
    a,b = float(np.median(ini)),float(np.median(final))
    delta=b-a
    sigma=max(dispersao(ini),dispersao(final))
    r.update(inicial_adc=a,final_adc=b,amplitude_adc=delta,sigma_adc=sigma,snr=abs(delta)/sigma,
             janela_observada_ms=float(t[-1]))
    # Falhas nao se convertem em 0 ms. O dado bruto permanece salvo.
    if abs(delta)<c.amplitude_minima:r['motivos'].append('sem_amplitude')
    if abs(delta)<c.snr_minimo*sigma:r['motivos'].append('relacao_sinal_ruido_insuficiente')
    if delta*(destino-origem)<=0:r['motivos'].append('polaridade_ou_estimulo_incompativel')
    # Um patamar preto na origem não implica corte da subida 10–90%.
    # A exceção exige que até o limiar de 10% já esteja fora do rail.
    preto_inicial = (cap.meta.get('source') == 'MCP3208' and origem == 0 and
                     delta > 0 and a <= 2 and a + .1*delta > 2)
    if np.any(y>=4093) or (np.any(y<=2) and not preto_inicial):
        r['motivos'].append('limite_adc_atingido')
    elif np.any(y<=2):
        r['avisos'].append('preto_inicial_no_limite_adc')
    if abs(delta)<20:
        r['avisos'].append('pequena_amplitude')
    if c.limite_analogico_alto is not None and np.any(y>=c.limite_analogico_alto):
        r['motivos'].append('limite_analogico_alto_informado')
    if c.limite_analogico_baixo is not None and np.any(y<=c.limite_analogico_baixo):
        r['motivos'].append('limite_analogico_baixo_informado')
    if cap.meta.get('legacy'):
        r['motivos'].append('legado_sem_timestamps_individuais_verificados')
    dt = np.diff(t)
    nominal = cap.meta.get('period_us',np.median(dt)*1000)/1000
    if (cap.meta.get('missed',0)>0 or np.any(dt>1.5*nominal) or
        abs(np.mean(dt)-nominal)>0.05*nominal or np.any(dt<0.5*nominal)):
        r['motivos'].append('temporizacao_irregular')
    if np.any(cap.leitura_us>=nominal*1000):r['motivos'].append('conversao_longa')
    if cap.meta.get('source')=='INTERNO':r['avisos'].append('adc_interno_sem_linearidade_verificada')
    for nome,x in [('inicial',ini),('final',final)]:
        blocos=np.array_split(x,4)
        drift=float(np.ptp([np.median(z) for z in blocos]))
        r[f'drift_{nome}_adc']=drift
        # Nao usar o desvio da janela inteira aqui: a propria deriva o inflaria.
        ruido_blocos=max(dispersao(z) for z in blocos)
        if drift>max(0.03*abs(delta),3*ruido_blocos):r['motivos'].append(f'patamar_{nome}_instavel')
    if referencia:
        for nome,valor,rgb in [('inicial',a,origem),('final',b,destino)]:
            ref=referencia.get(int(rgb))
            if ref and abs(valor-ref['mediana'])>max(20,5*ref['sigma'],0.05*abs(delta)):
                r['motivos'].append(f'patamar_{nome}_diverge_da_varredura')
    if r['motivos']:
        return r
    p = (median_filter(y,size=c.mediana_amostras,mode='nearest')-a)/delta
    rawp = (y-a)/delta
    t10 = cruzamento(t,p,0.1,c.patamar_inicial_ms,c.persistencia_ms)
    if t10 is None:
        r['motivos'].append('cruzamento_10_ausente');return r
    t90 = cruzamento(t,p,0.9,t10,c.persistencia_ms)
    if t90 is None:
        r['motivos'].append('cruzamento_90_ausente');return r
    if t10<=c.patamar_inicial_ms+1 or t90>=t[-1]-c.patamar_final_ms:
        r['motivos'].append('transicao_fora_da_janela_util');return r
    if preto_inicial and np.any(y[t >= t10+c.persistencia_ms]<=2):
        r['motivos'].append('limite_adc_atingido');return r
    if t90-t10<3*np.median(dt):
        r['motivos'].append('resposta_sub_resolucao_temporal');return r
    inicio=np.searchsorted(t,t10)
    fim=np.searchsorted(t,t[-1]-c.patamar_final_ms)
    over=100*max(0,float(np.max(p[inicio:fim]))-1)
    overraw=100*max(0,float(np.max(rawp[inicio:fim]))-1)
    piso=300*sigma/abs(delta)
    r.update(status='OK_ALGORITMO',valida=True,t10_ms=t10,t90_ms=t90,g2g_ms=t90-t10,
             overshoot_pct=over,overshoot_bruto_pct=overraw,
             piso_indicativo_overshoot_pct=piso,overshoot_detectado=over>piso,
             excursao_oposta_pct=100*max(0,-float(np.min(p[inicio:fim]))),
             suporte_filtro_ms=(c.mediana_amostras-1)*float(np.median(dt)))
    if over<=piso:r['avisos'].append('overshoot_nao_distinguivel_do_ruido')
    if overraw-over>piso:r['avisos'].append('pico_sensivel_ao_filtro')
    # Tempo desde t10 ate a ultima entrada na faixa; nao inclui latencia do PC.
    # Exige permanencia em TODA a cauda observada, com pelo menos 20 ms.
    banda=c.tolerancia_acomodacao
    if 3*sigma/abs(delta)>banda:
        r['acomodacao_status']='RUIDO_EXCEDE_FAIXA'
    else:
        fora=np.flatnonzero((abs(p-1)>banda)&(t>=t10))
        ultimo=int(fora[-1]) if len(fora) else inicio-1
        entrada=ultimo+1
        if entrada>=len(t) or t[-1]-t[entrada]<c.permanencia_final_ms:
            r['acomodacao_status']='NAO_CONFIRMADA_NA_JANELA'
        else:
            r.update(acomodacao_status='CONFIRMADA_NA_JANELA',
                     acomodacao_ms=float(t[entrada]-t10),
                     acomodacao_confirmada_ate_ms=float(t[-1]-t10))
    # Indicador de sensibilidade temporal, nao incerteza metrologica completa.
    slopes=[]
    for momento in (t10,t90):
        j=int(np.searchsorted(t,momento));lo=max(0,j-2);hi=min(len(t)-1,j+2)
        slopes.append(abs((p[hi]-p[lo])/(t[hi]-t[lo])))
    r['sensibilidade_ruido_ms']=float(sum((sigma/abs(delta))/max(v,1e-9) for v in slopes))
    return r


def avaliar_varredura(rows):
    """Teste relativo de monotonicidade/repetibilidade; nao calibra gamma nem volts."""
    refs={};avisos=[];problemas=set()
    for rgb in sorted(set(x['rgb'] for x in rows)):
        grupo=[x for x in rows if x['rgb']==rgb]
        medianas=[x['mediana'] for x in grupo]
        sigma=max(x['desvio_padrao'] for x in grupo)+0.5
        refs[rgb]=dict(mediana=float(np.median(medianas)),sigma=sigma)
        if np.ptp(medianas)>max(20,5*sigma):
            avisos.append(f'RGB {rgb}: deriva entre repeticoes/ordens');problemas.add(rgb)
        if any(x['fracao_rail']>0 for x in grupo):
            avisos.append(f'RGB {rgb}: limite ADC');problemas.add(rgb)
        if any(x.get('temporizacao_valida') is False for x in grupo):
            avisos.append(f'RGB {rgb}: temporizacao irregular/nao verificada');problemas.add(rgb)
    niveis=sorted(refs)
    for a,b in zip(niveis[:-1],niveis[1:]):
        d=refs[b]['mediana']-refs[a]['mediana']
        lim=max(10,3*max(refs[a]['sigma'],refs[b]['sigma']))
        if d<=lim:
            avisos.append(f'RGB {a}->{b}: patamares nao separados; compressao/ruido/estimulo a investigar')
            problemas.update((a,b))
    return dict(referencia=refs,avisos=avisos,niveis_problematicos=sorted(problemas),
                aprovada_relativamente=not avisos)


def espectro(cap):
    """Espectro exploratorio. Bloqueia FFT comum se tempos forem irregulares."""
    t=np.asarray(cap.t_us,float)/1e6
    dt=np.diff(t)
    if np.any(dt<=0) or np.max(abs(dt-np.median(dt)))>0.05*np.median(dt):
        return None
    y=np.asarray(cap.adc,float);w=np.hanning(len(y))
    f=np.fft.rfftfreq(len(y),np.median(dt))
    amplitude=2*abs(np.fft.rfft((y-y.mean())*w))/w.sum()
    return f,amplitude
