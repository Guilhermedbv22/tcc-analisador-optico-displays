from pathlib import Path
from PySide6.QtCore import QThread, Signal, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QPushButton,QComboBox,
 QLineEdit,QCheckBox,QFileDialog,QApplication,QSpinBox,QInputDialog,QProgressBar)
from .widgets import label,scroll,table,fill_table,card
from ..campaign import Campaign
from ..campaign_export import export_campaign
from ..acquisition import progress_text
from ..publication import publish_package,DEFAULT_SITE


class CampaignJob(QThread):
    progress=Signal(str);completed=Signal(object);failed=Signal(str)
    def __init__(self,fn,parent=None):super().__init__(parent);self.fn=fn
    def run(self):
        try:self.completed.emit(self.fn(self.progress.emit))
        except Exception as exc:self.failed.emit(str(exc))


class CampaignPage(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.campaign=None;self.active=None;self.worker=None;self.mapping={};self.last_export=None
        outer=QVBoxLayout(self);w=QWidget();v=QVBoxLayout(w)
        v.addWidget(label('Campanha de ensaios','title'))
        v.addWidget(label('Roteiro técnico com matrizes, ADCs, repetibilidade e capacitores.','muted',True))
        row=QHBoxLayout();self.campaigns=QComboBox();row.addWidget(self.campaigns,1)
        self.new=QPushButton('Nova campanha');row.addWidget(self.new);self.new.clicked.connect(lambda:app.guard(self.create))
        self.load=QPushButton('Abrir / retomar');row.addWidget(self.load);self.load.clicked.connect(lambda:app.guard(self.load_selected));v.addLayout(row)
        setup,cv=card('Preparação única','Os ajustes já registrados ficam salvos. Confira a tela correta e as condições antes de continuar. A frequência deve ser selecionada no Windows quando o roteiro pedir.')
        f=QFormLayout()
        for mon in ('LG','AOC','HQ'):
            cb=QComboBox();self.mapping[mon]=cb;f.addRow('Tela de estímulo · '+mon,cb)
        b=QPushButton('Atualizar telas conectadas');b.clicked.connect(self.refresh_screens);f.addRow(b)
        self.assembly=QComboBox();self.assembly.addItems(['Protoboard','Placa definitiva']);f.addRow('Montagem realmente utilizada',self.assembly)
        self.warmup=QSpinBox();self.warmup.setRange(0,1440);self.warmup.setSuffix(' min');self.warmup.setValue(60);f.addRow('Aquecimento realizado nos monitores',self.warmup)
        self.ambient=QLineEdit();self.ambient.setPlaceholderText('Opcional · temperatura e iluminação; vazio = não informado');f.addRow('Ambiente',self.ambient)
        self.warmed=QCheckBox('Conferi o aquecimento e as condições informadas.');f.addRow(self.warmed)
        cv.addLayout(f);self.profiles=label('','muted',True);cv.addWidget(self.profiles);v.addWidget(setup)
        self.plan=table(['Etapa','Monitor / Hz / overdrive','Estado','Capturas salvas']);self.plan.setMinimumHeight(230)
        self.plan.itemSelectionChanged.connect(self.selection_changed);v.addWidget(self.plan)
        self.instruction=label('Crie uma campanha para começar.','heading',True);v.addWidget(self.instruction)
        self.confirm=QCheckBox('Fiz a alteração indicada, conferi o monitor e posso iniciar esta etapa.');v.addWidget(self.confirm)
        self.autorun=QCheckBox('Continuar automaticamente nas etapas que não exigem nova intervenção física.');self.autorun.setChecked(True);v.addWidget(self.autorun)
        row=QHBoxLayout()
        self.start=QPushButton('Iniciar / retomar etapa');self.start.setObjectName('primary');row.addWidget(self.start);self.start.clicked.connect(lambda:app.guard(self.begin))
        self.stop=QPushButton('Pausar após a captura atual');row.addWidget(self.stop);self.stop.clicked.connect(app.acquisition.cancel);self.stop.setEnabled(False)
        self.retry=QPushButton('Repetir etapa · nova sessão');row.addWidget(self.retry);self.retry.clicked.connect(lambda:app.guard(self.repeat))
        self.skip=QPushButton('Pular etapa com motivo');row.addWidget(self.skip);self.skip.clicked.connect(lambda:app.guard(self.skip_step));v.addLayout(row)
        self.retry_invalid=QPushButton('Repetir só as transições inválidas · preservar o ensaio original')
        self.retry_invalid.clicked.connect(lambda:app.guard(self.repeat_invalid));v.addWidget(self.retry_invalid)
        self.progress=QProgressBar();v.addWidget(self.progress)
        self.live=label('Pronto.','muted',True);v.addWidget(self.live)
        row=QHBoxLayout();self.export=QPushButton('Exportar pacote completo');self.export.setObjectName('primary');row.addWidget(self.export);self.export.clicked.connect(lambda:app.guard(self.export_all))
        self.open=QPushButton('Abrir pasta do pacote');row.addWidget(self.open);self.open.clicked.connect(self.open_folder);v.addLayout(row)
        self.public_consent=QCheckBox('Revisei as sessões completas e quero publicar os relatórios dos monitores.');v.addWidget(self.public_consent)
        self.send=QPushButton('Enviar relatórios dos monitores ao site');self.send.clicked.connect(lambda:app.guard(self.send_all));v.addWidget(self.send)
        self.status=label('Os ensaios funcionam offline. Gere o pacote antes de publicar.','muted',True);self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);v.addWidget(self.status)
        v.addStretch();outer.addWidget(scroll(w))
        app.acquisition.session_started.connect(self.session_started)
        app.acquisition.finished.connect(self.finished)
        app.acquisition.progress_detail.connect(self.update_progress)
        self.refresh_screens();self.refresh_campaigns()
        id=app.store.setting('active_campaign')
        if id and (app.store.root/'campaigns'/id/'campaign.json').exists():
            self.campaign=Campaign.load(app.store,id);self.populate()

    def refresh_campaigns(self):
        self.campaigns.clear()
        for p in sorted((self.app.store.root/'campaigns').glob('*/campaign.json'),reverse=True):self.campaigns.addItem(p.parent.name,p.parent.name)
        if self.campaign:self.campaigns.setCurrentIndex(self.campaigns.findData(self.campaign.data['id']))

    def refresh_screens(self):
        for mon,cb in self.mapping.items():
            old=cb.currentData();cb.clear()
            for i,s in enumerate(QApplication.screens()):
                g=s.geometry();cb.addItem(f'{i+1} · {s.name()} · {g.width()}×{g.height()} · {s.refreshRate():.2f} Hz',i)
            ix=cb.findData(old);cb.setCurrentIndex(max(ix,0))

    def ensure_idle(self):
        self.app.check_idle()
        if self.busy():raise ValueError('Aguarde a exportação ou publicação terminar.')

    def create(self):
        self.ensure_idle();self.campaign=Campaign.create(self.app.store);self.populate();self.refresh_campaigns()

    def load_selected(self):
        self.ensure_idle();id=self.campaigns.currentData()
        if not id:raise ValueError('Crie uma campanha primeiro.')
        self.campaign=Campaign.load(self.app.store,id);self.app.store.set_setting('active_campaign',id);self.populate()

    def populate(self):
        c=self.campaign
        self.assembly.setCurrentText(c.data['assembly']);self.warmup.setValue(c.data['warmup_min']);self.ambient.setText(c.data['ambient']);self.warmed.setChecked(c.data['warmup_confirmed'])
        for mon,cb in self.mapping.items():
            ix=cb.findData(c.data.get('screens',{}).get(mon,0));cb.setCurrentIndex(max(ix,0))
        self.profiles.setText('LG: Adaptive Sync Extended · Black Stabilizer 50 · brilho 100 · contraste 50 · sharpness 50 · RGB 45/47/49 · DFC Off · DisplayPort · DAS On.\nHQ: brilho 100 · contraste 50 · HDMI. AOC LM522: VGA; brilho/contraste não informados.\nCircuito: MCP6022 + MCP3208 em 3,3 V · Rf 235 kΩ · Cf 8,2 pF · reserva geral 4,7 µF · ganho fixo.')
        self.refresh_plan();next=c.next_step();self.select(next)
        if c.data['exports']:self.last_export=c.data['exports'][-1]

    def selected(self):
        i=self.plan.currentRow()
        return self.campaign.data['steps'][i] if self.campaign and i>=0 else None

    def select(self,s):
        if s:self.plan.selectRow(self.campaign.data['steps'].index(s))
        self.selection_changed()

    def refresh_plan(self):
        if not self.campaign:return
        i=self.plan.currentRow();self.plan.blockSignals(True)
        fill_table(self.plan,[[s['title'],f"{s['monitor']} · {s['hz']} Hz · {s['overdrive']}",s['status'],
          f"{len(s['tasks'])-len(self.campaign.remaining(s))}/{len(s['tasks'])}"] for s in self.campaign.data['steps']])
        if i>=0:self.plan.selectRow(i)
        self.plan.blockSignals(False)

    def selection_changed(self):
        s=self.selected();self.confirm.setChecked(False)
        if not s:return
        instruction=f"{s['title']}\nSelecione {s['monitor']} a {s['hz']} Hz e overdrive {s['overdrive']}. ADC: {s['adc']}.\n"+s['instruction']
        if s['kind']=='monitor':instruction+='\n72 transições × 5 repetições; referências iniciais e finais. Todos os capacitores instalados; GPIO34 sem jumper.'
        if s['session_id']:instruction+='\n'+self.campaign.report(s)
        self.instruction.setText(instruction)

    def save_setup(self):
        c=self.campaign
        c.data.update(assembly=self.assembly.currentText(),warmup_min=self.warmup.value(),ambient=self.ambient.text().strip(),warmup_confirmed=self.warmed.isChecked(),screens={mon:cb.currentData() for mon,cb in self.mapping.items()})
        c.save()

    def begin(self,automatic=False):
        self.ensure_idle();s=self.selected()
        if not s:raise ValueError('Crie a campanha e selecione uma etapa.')
        if s['status'] in ('concluida','revisar','pulada'):raise ValueError('Etapa já encerrada. Use Repetir etapa para criar outra sessão sem apagar a anterior.')
        if not self.warmed.isChecked():raise ValueError('Registre e confira o aquecimento antes de medir.')
        if not automatic and not self.confirm.isChecked():raise ValueError('Faça a alteração indicada e marque a confirmação antes de iniciar.')
        self.save_setup();screen=self.mapping[s['monitor']].currentData();screens=QApplication.screens()
        if screen is None or screen>=len(screens):raise ValueError('Atualize as telas e selecione o monitor conectado.')
        current=screens[screen];hz=current.refreshRate()
        if abs(hz-s['hz'])>2:raise ValueError(f"O Windows informa {hz:.2f} Hz. Selecione {s['hz']} Hz nas configurações de vídeo e atualize as telas.")
        g=current.geometry();dpr=current.devicePixelRatio();cfg=self.campaign.config(s,screen,f'{round(g.width()*dpr)}×{round(g.height()*dpr)}')
        self.campaign.prepare_resume(s);remaining=self.campaign.remaining(s)
        if not remaining:
            s['status']='revisar';self.campaign.save();self.refresh_plan();return
        self.active=s['id'];self.set_busy(True,acquisition=True)
        try:self.app.acquisition.start(cfg,sid=s['session_id'],tasks=remaining,provenance={'campaign':self.campaign.data['id'],'step':s['id'],'procedure':'iris-campaign/1'})
        except Exception:
            self.active=None;self.set_busy(False);raise

    def session_started(self,sid):
        if self.active:self.campaign.attach(self.campaign.step(self.active),sid);self.refresh_plan()

    def update_progress(self,data):
        if not self.active:return
        self.live.setText(progress_text(data))
        self.progress.setRange(0,max(data['total'],1));self.progress.setValue(data['completed'])

    @staticmethod
    def signature(s):
        return (s['monitor'],s['hz'],s['overdrive'],s['caps'],s['setup'])

    def finished(self,sid,status):
        if not self.active:return
        s=self.campaign.step(self.active)
        if sid!=s['session_id']:return
        self.campaign.complete(s,status);self.active=None;self.set_busy(False);self.refresh_plan()
        if self.campaign.adapt_diagnostic(s,status):
            self.refresh_plan();self.select(s)
            self.status.setText('O diagnóstico indicou janela insuficiente ou patamar final instável. Repetindo uma vez com 600 ms, sem mudar os critérios. As duas aquisições serão preservadas.')
            QTimer.singleShot(350,lambda:self.app.guard(lambda:self.begin(automatic=True)))
            return
        message=self.campaign.report(s);self.status.setText(s['title']+'\n'+message)
        next=self.campaign.next_step()
        if self.campaign.remaining(s):self.select(s);return
        self.select(next)
        # Só avança sem interação quando a condição física não muda e o diagnóstico não falhou.
        rows=self.app.store.rows(sid);measured=[r for r in rows if r['phase']=='medicao']
        healthy=(status=='concluida' and (s['kind']!='diagnostico' or any(r.get('valida') for r in measured)))
        if next and healthy and self.autorun.isChecked() and self.signature(s)==self.signature(next):
            QTimer.singleShot(350,lambda:self.app.guard(lambda:self.begin(automatic=True)))
        elif next:self.status.setText(message+'\nPróxima etapa pronta. Confira a instrução e clique em Iniciar.')
        else:self.status.setText(message+'\nRoteiro encerrado. Gere o pacote completo e revise os relatórios.')

    def repeat(self):
        self.ensure_idle();s=self.selected()
        if s:self.campaign.repeat(s);self.refresh_plan();self.selection_changed()

    def repeat_invalid(self):
        self.ensure_idle();s=self.selected()
        if s:
            new=self.campaign.retry_invalid(s);self.refresh_plan();self.select(new)

    def skip_step(self):
        self.ensure_idle();s=self.selected()
        if not s:return
        reason,ok=QInputDialog.getText(self,'Registrar etapa não realizada','Motivo:')
        if ok and reason.strip():
            s['status']='pulada';self.campaign.record('etapa_pulada',step=s['id'],reason=reason.strip());self.refresh_plan();self.select(self.campaign.next_step())

    def busy(self):return self.worker is not None and self.worker.isRunning()

    def set_busy(self,value,acquisition=False):
        for b in [self.start,self.retry,self.retry_invalid,self.skip,self.export,self.send,self.new,self.load,self.plan,self.confirm,self.warmed,self.assembly,self.warmup,self.ambient,self.public_consent,*self.mapping.values()]:b.setEnabled(not value)
        self.stop.setEnabled(value and acquisition)

    def run_job(self,fn,done):
        self.set_busy(True);self.worker=CampaignJob(fn,self)
        self.worker.progress.connect(self.status.setText);self.worker.completed.connect(done)
        self.worker.failed.connect(lambda message:self.status.setText('Operação interrompida: '+message+'\nOs dados salvos permanecem disponíveis; tente novamente após corrigir.'))
        self.worker.finished.connect(lambda:(self.set_busy(False),self.app.busy_changed()));self.worker.start();self.app.busy_changed()

    def export_all(self):
        self.ensure_idle()
        if not self.campaign:raise ValueError('Crie uma campanha primeiro.')
        self.save_setup()
        self.run_job(lambda progress:export_campaign(self.campaign,progress),self.exported)

    def exported(self,result):
        self.last_export=result;self.status.setText('Pacote completo: '+result['path']+'\nAbra a pasta para localizar o ZIP.');self.app.notify('Pacote da campanha gerado.')

    def open_folder(self):
        if self.last_export:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_export['path'] if 'path' in self.last_export else self.last_export['zip']).parent)))
        elif self.campaign:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.campaign.folder)))

    def send_all(self):
        self.ensure_idle()
        if not self.campaign or not self.public_consent.isChecked():raise ValueError('Revise as sessões e marque a opção de publicação.')
        pending=[(s,p) for s in self.campaign.data['steps'] if s['kind']=='monitor' for p in s['publications'] if p['state']!='publicado']
        if not pending:raise ValueError('Gere o pacote completo primeiro. Só sessões completas de monitor são preparadas para o site.')
        site=self.app.store.setting('publication_site',DEFAULT_SITE)
        def publish(progress):
            results=[]
            for s,p in pending:
                progress('Enviando '+s['title']+' · '+Path(p['path']).parent.name)
                try:
                    receipt=publish_package(p['path'],site);p.update(state='publicado',url=receipt['url'],id=receipt['id']);results.append(receipt['url'])
                except Exception as exc:p.update(state='falha',error=str(exc))
                self.campaign.save()
            # Guarda os links também em um arquivo simples para consulta.
            urls=[p['url'] for s in self.campaign.data['steps'] for p in s['publications'] if p.get('url')]
            (self.campaign.folder/'links_publicados.txt').write_text('\n'.join(urls),encoding='utf8')
            return dict(urls=urls,failed=sum(p['state']=='falha' for s,p in pending))
        self.run_job(publish,lambda result:self.status.setText(f"{len(result['urls'])} relatórios publicados; {result['failed']} falhas.\n"+'\n'.join(result['urls'])+'\nFalhas podem ser reenviadas pelo mesmo botão. Gere outro pacote para incluir os links.'))
