"""Campanha local persistente. Protocolos fixos, retomada por tarefa e proveniência."""
from copy import deepcopy
from pathlib import Path
import json
import uuid
from .config import TestConfig
from .storage import atomic, json_text, utc

LEVELS = [0, 32, 64, 96, 128, 160, 192, 224, 255]
PAIRS = [(0,255),(255,0),(51,153),(153,51),(0,32),(32,0)]
PROFILES = {
 'LG': dict(model='LG UltraGear 24GS60F-B', hz=180, brightness='100', contrast='50', settings={
  'adaptive_sync':'Extended','black_stabilizer':50,'sharpness':50,'R':45,'G':47,'B':49,
  'DFC':'Off','connection':'DisplayPort','DAS Mode':'On'}),
 'HQ': dict(model='15.6HQ-LED', hz=60, brightness='100', contrast='50', settings={'connection':'HDMI'}),
 'AOC': dict(model='AOC LM522', hz=60, brightness='', contrast='', settings={'connection':'VGA'}),
}
CAPS = dict(C_OP_100nF=True, C_ADC_100nF=True, C_REF_100nF=True, C_MID_100nF=True, bulk_uF=4.7, feedback_pF=8.2)
CAP_NAMES = {
 'C_OP_100nF':'100 nF entre pinos 8 e 4 do MCP6022',
 'C_ADC_100nF':'100 nF entre VDD (pino 16) e GND do MCP3208',
 'C_REF_100nF':'100 nF entre VREF (pino 15) e AGND do MCP3208',
 'bulk_uF':'4,7 µF geral entre 3,3 V e GND, compartilhado pelos dois MCPs',
 'feedback_pF':'8,2 pF entre pinos 1 e 2 do MCP6022 (em paralelo com Rf)',
}


def task(a,b,r=1,phase='medicao'):
    return dict(origin=a,destination=b,repetition=r,phase=phase)


def fixed_tasks(pairs=PAIRS, repetitions=10, references=True):
    levels=sorted({x for pair in pairs for x in pair})
    before=[task(x,x,phase='referencia_antes') for x in levels] if references else []
    after=[task(x,x,phase='referencia_depois') for x in reversed(levels)] if references else []
    return before+[task(a,b,r) for r in range(1,repetitions+1) for a,b in pairs]+after


def key(t):
    return (t['phase'],t['origin'],t['destination'],t['repetition'])


def planned_steps():
    steps=[]
    def add(id,title,monitor='LG',hz=180,od='Fast',kind='auxiliar',tasks=None,adc='MCP3208',caps=None,setup='normal',instruction=''):
        steps.append(dict(id=id,title=title,monitor=monitor,hz=hz,overdrive=od,kind=kind,
          tasks=tasks or fixed_tasks(),adc=adc,caps=deepcopy(caps or CAPS),setup=setup,
          instruction=instruction,status='pendente',session_id=None,attempts=[],publications=[]))
    for mon,hz,ods in [('LG',180,['Fast','Normal','Desligado','Faster']),('LG',60,['Fast']),('AOC',60,['Configuração única']),('HQ',60,['Configuração única'])]:
        if mon!='LG' or hz==180:
            add(f'diag_{mon}',f'Diagnóstico inicial · {mon}',mon,hz,ods[0],'diagnostico',fixed_tasks([(0,255),(255,0),(0,32),(32,0)],1),instruction='Circuito completo; fixe a sonda no centro do quadrado. Confira luz ambiente e aquecimento. O diagnóstico não altera o ganho nem relaxa os critérios.')
        for od in ods:
            pairs=[(a,b) for a in LEVELS for b in LEVELS if a!=b]
            add(f'monitor_{mon}_{hz}_{od}',f'{mon} · {hz} Hz · {od} · matriz completa',mon,hz,od,'monitor',fixed_tasks(pairs,5))
    add('overdrive_fast','Overdrive detalhado · Fast',tasks=fixed_tasks([(0,153),(153,0),(255,204),(0,32)],20))
    add('overdrive_faster','Overdrive detalhado · Faster',od='Faster',tasks=fixed_tasks([(0,153),(153,0),(255,204),(0,32)],20))
    static=[task(x,x,r,'estatica') for r in range(1,6) for x in LEVELS]
    instruction='Desligue o circuito. Ligue temporariamente CH0 do MCP3208 (após os 100 Ω) ao GPIO34. Religue, reconecte o ESP32 e confirme. Mantenha esse jumper em TODOS os blocos de comparação; as leituras são sequenciais.'
    for source in ['MCP3208','INTERNO']:
        add('adc_static_'+source,'ADC · patamares · '+source,kind='adc',tasks=static,adc=source,setup='jumper_adc',instruction=instruction)
    for block,source in enumerate(['MCP3208','INTERNO','MCP3208','INTERNO'],1):
        add(f'adc_dynamic_{block}',f'ADC · bloco {block} · {source}',kind='adc',tasks=fixed_tasks(repetitions=5),adc=source,setup='jumper_adc',instruction=instruction)
    add('repeat_fixed','Repetibilidade · sonda mantida',kind='repetibilidade',tasks=fixed_tasks([(0,153),(255,204),(0,32),(32,0)],20),instruction='Desligue e retire o jumper CH0–GPIO34; religue e reconecte. Mantenha a sonda fixa durante este bloco.')
    add('repeat_reposition','Repetibilidade · após reposicionar',kind='repetibilidade',tasks=fixed_tasks([(0,153),(255,204),(0,32),(32,0)],20),setup='reposicionada',instruction='Retire a sonda e reposicione-a no centro, com a mesma proteção contra luz. Este bloco registra um novo posicionamento, não uma calibração.')
    caps_tasks=[task(x,x,r,'estatica') for r in range(1,6) for x in (32,128,224)]+fixed_tasks([(0,153),(153,0),(0,32),(32,0)],5,False)
    add('caps_reference','Capacitores · referência inicial',kind='capacitores',tasks=caps_tasks,setup='caps',instruction='Circuito completo, jumper GPIO34 retirado. A partir daqui não movimente a sonda. Faça mudanças somente com alimentação desligada.')
    for name in CAP_NAMES:
        caps=deepcopy(CAPS);caps[name]=0 if name in ('bulk_uF','feedback_pF') else False
        add('caps_'+name,'Capacitores · sem '+name,kind='capacitores',tasks=caps_tasks,caps=caps,setup='caps',instruction='Desligue. REINSTALE todos os componentes da etapa anterior. Retire SOMENTE: '+CAP_NAMES[name]+'. Mantenha o capacitor do MID. Religue e reconecte o ESP32. Sem 8,2 pF, alterações de pico podem pertencer ao TIA.')
    add('caps_restored','Capacitores · referência restaurada',kind='capacitores',tasks=caps_tasks,setup='caps',instruction='Desligue e REINSTALE TODOS os capacitores. Religue e reconecte. Mantenha a sonda na mesma posição da referência inicial.')
    return steps


class Campaign:
    def __init__(self,store,data):
        self.store,self.data=store,data
        self.folder=store.root/'campaigns'/data['id']
        self.folder.mkdir(parents=True,exist_ok=True)

    @classmethod
    def create(cls,store):
        data=dict(schema='iris-campaign/1',id='campanha_'+uuid.uuid4().hex[:10],created=utc(),
          profiles=deepcopy(PROFILES),assembly='Protoboard',ambient='',warmup_min=60,
          warmup_confirmed=False,steps=planned_steps(),events=[],exports=[])
        obj=cls(store,data);obj.save();store.set_setting('active_campaign',data['id']);return obj

    @classmethod
    def load(cls,store,id):
        if Path(id).name!=id:raise ValueError('Identificação de campanha inválida.')
        obj=cls(store,json.loads((store.root/'campaigns'/id/'campaign.json').read_text(encoding='utf8')))
        obj.reconcile();return obj

    def save(self):
        self.data['updated']=utc()
        atomic(self.folder/'campaign.json',json_text(self.data).encode('utf8'))

    def record(self,event,**details):
        self.data['events'].append(dict(time=utc(),event=event,**details));self.save()

    def step(self,id):
        return next(s for s in self.data['steps'] if s['id']==id)

    def remaining(self,s):
        done=set()
        if s['session_id']:
            for row in self.store.rows(s['session_id']):
                # Uma captura recebida sem análise será reanalisada ao retomar, não perdida.
                done.add((row['phase'],row['origem_rgb'],row['destino_rgb'],row['repetition']))
        return [t for t in s['tasks'] if key(t) not in done]

    def reconcile(self):
        for s in self.data['steps']:
            if s['status']=='em_andamento':
                s['status']='interrompida' if self.remaining(s) else 'revisar'
                if s['session_id']:
                    self.store.finish(s['session_id'],'interrompida' if self.remaining(s) else 'revisar_referencias')
        self.save()

    def config(self,s,screen_index,resolution):
        if s['session_id']:
            cfg=TestConfig.from_dict(self.store.get_session(s['session_id'])['config'])
            if cfg.resolution!=resolution:
                raise ValueError('A resolução mudou desde a interrupção. Restaure-a ou use Repetir etapa para abrir outra sessão.')
            cfg.screen=screen_index;return cfg
        p=self.data['profiles'][s['monitor']]
        pairs=list(dict.fromkeys((t['origin'],t['destination']) for t in s['tasks'] if t['origin']!=t['destination'])) or [(0,255)]
        return TestConfig(title=f"{self.data['id']} · {s['title']}",monitor=p['model'],refresh_hz=s['hz'],overdrive=s['overdrive'],
          brightness=p['brightness'],contrast=p['contrast'],monitor_settings=deepcopy(p['settings']),
          resolution=resolution,hdr='Não informado',vrr=p['settings'].get('adaptive_sync','Não informado'),
          warmup_min=self.data['warmup_min'],ambient=self.data['ambient'],assembly=self.data['assembly'],
          adc=s['adc'],rf_kohm=235,cf_pf=s['caps']['feedback_pF'],capacitors=deepcopy(s['caps']),
          rate_sps=10000,window_ms=s.get('window_ms',300),pre_ms=75,hold_ms=500,spi_hz=1000000,
          levels=9,repetitions=max(t['repetition'] for t in s['tasks']),custom_pairs=','.join(f'{a}>{b}' for a,b in pairs),
          randomize=False,screen=screen_index,patch_area_percent=10,background_rgb=127,
          static_references=any(t['phase'].startswith('referencia') for t in s['tasks']),
          campaign_id=self.data['id'],campaign_step=s['id'],notes='Protocolo guiado fixo; aquecimento confirmado pelo operador. Alterações elétricas manuais; sem autoranging.').validate()

    def attach(self,s,sid):
        s['session_id']=sid
        if sid not in s['attempts']:s['attempts'].append(sid)
        s['status']='em_andamento';self.save()

    def complete(self,s,status):
        s['last_status']=status
        s['status']=('concluida' if status=='concluida' else 'revisar') if not self.remaining(s) else 'interrompida'
        self.save()

    def repeat(self,s):
        s['session_id']=None;s['status']='pendente';s['publications']=[]
        self.record('repetir_etapa',step=s['id'],previous_attempts=list(s['attempts']))

    def next_step(self):
        return next((s for s in self.data['steps'] if s['status'] not in ('concluida','revisar','pulada')),None)

    def adapt_diagnostic(self,s,status):
        if s['kind']!='diagnostico' or status in ('cancelada','falha') or s.get('window_ms',300)>=600:
            return False
        rows=self.store.rows(s['session_id'])
        reasons={reason for r in rows for reason in r.get('motivos',[])}
        if not reasons.intersection({'patamar_final_instavel','cruzamento_90_ausente','transicao_fora_da_janela_util'}):
            return False
        if reasons.intersection({'temporizacao_irregular','conversao_longa','zero_continuo','codigo_constante'}):
            return False
        for step in self.data['steps']:
            if step['monitor']==s['monitor'] and not step['session_id']:step['window_ms']=600
        s['window_ms']=600;self.repeat(s)
        self.record('janela_ampliada',monitor=s['monitor'],window_ms=600,reasons=sorted(reasons))
        return True

    def retry_invalid(self,s):
        if not s['session_id']:raise ValueError('Esta etapa ainda não tem aquisições.')
        invalid={(r['origem_rgb'],r['destino_rgb'],r['repetition']) for r in self.store.rows(s['session_id']) if r['phase']=='medicao' and not r.get('valida')}
        if not invalid:raise ValueError('Não há transições inválidas nesta etapa.')
        new=deepcopy(s);new.update(id=s['id']+'_reteste_'+uuid.uuid4().hex[:5],title='Reteste · '+s['title'],kind='reteste',
          status='pendente',session_id=None,attempts=[],publications=[],source_session=s['session_id'])
        new['tasks']=[t for t in s['tasks'] if t['phase'].startswith('referencia') or (t['phase']=='medicao' and (t['origin'],t['destination'],t['repetition']) in invalid)]
        self.data['steps'].append(new);self.record('reteste_invalidas',source=s['session_id'],step=new['id'],transitions=len(invalid))
        return new

    def report(self,s):
        if not s['session_id']:return 'Sem capturas.'
        rows=self.store.rows(s['session_id']);measured=[r for r in rows if r['phase']=='medicao']
        valid=sum(bool(r.get('valida')) for r in measured)
        from collections import Counter
        reasons=Counter(reason for r in measured if not r.get('valida') for reason in r.get('motivos',[]))
        return f"{len(rows)}/{len(s['tasks'])} capturas · {valid}/{len(measured)} transições válidas. "+'; '.join(f'{k}: {v}' for k,v in reasons.most_common(3))

    def prepare_resume(self,s):
        if not s['session_id']:return
        from .analysis import analyze
        cfg=TestConfig.from_dict(self.store.get_session(s['session_id'])['config'])
        for row in self.store.rows(s['session_id']):
            if row.get('analysis_version') is None:
                self.store.save_analysis(row['capture_id'],analyze(self.store.capture(row['capture_id']),row['origem_rgb'],row['destino_rgb'],cfg.get_criteria()))
