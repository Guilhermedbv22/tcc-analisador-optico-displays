import json
import time
from pathlib import Path
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,
    QLineEdit,QCheckBox,QPushButton,QFileDialog,QTabWidget,QPlainTextEdit,QInputDialog)
from .widgets import label,spin,combo,table,fill_table,Metric,plot_widget,COLORS,fmt,scroll
from ..device import RANGE_NAMES
from ..exports import write_csv,report_html,report_pdf,export_csv
from ..analysis import analyze
from ..core.nucleo import estatisticas,espectro


class BenchPage(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.running=False;self.pending=None;self.sid=None
        self.data=[];self.latest={};self.todo=[];self.stopping=False;self.callbacks={}
        self.snapshot_pending=False
        layout=QVBoxLayout(self)
        layout.addWidget(label("Diagnóstico do sinal","heading"))
        layout.addWidget(label("MCP3208: entrada de 0 a VREF, sempre dentro de GND..VDD. Referência informada deve corresponder ao circuito. Não medir 5 V diretamente; esta ferramenta não substitui teste de continuidade sem alimentação.","muted",True))
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        live=QWidget();live.setMinimumHeight(730);v=QVBoxLayout(live);self.tabs.addTab(scroll(live),"Voltímetro")
        form=QGridLayout();self.title=QLineEdit("Leitura de diagnóstico");form.addWidget(label("Identificação"),0,0);form.addWidget(self.title,0,1,1,3)
        self.vref=spin(app.store.setting("vref",3.3),.1,3.6,4," V");form.addWidget(label("VREF física"),0,4);form.addWidget(self.vref,0,5)
        self.interval=spin(500,150,60000,0," ms / ciclo");form.addWidget(label("Intervalo"),1,4);form.addWidget(self.interval,1,5)
        self.source=combo(["MCP3208","INTERNO"]);form.addWidget(label("ADC"),1,0);form.addWidget(self.source,1,1)
        self.raw=QCheckBox("Gráfico em códigos ADC");form.addWidget(self.raw,1,2,1,2);self.raw.toggled.connect(self.draw)
        v.addLayout(form)
        row=QHBoxLayout();row.addWidget(label("Canais"));self.channels=[]
        for ch in range(8):
            w=QCheckBox(f"CH{ch}");w.setChecked(ch==0);self.channels.append(w);row.addWidget(w)
        row.addStretch();v.addLayout(row)
        met=QHBoxLayout();self.voltage=Metric("Última tensão · canal selecionado");met.addWidget(self.voltage)
        self.codes=Metric("Média de 64 leituras",COLORS[1]);met.addWidget(self.codes)
        self.delta=Metric("Diferença CH1 − CH0",COLORS[2]);met.addWidget(self.delta);v.addLayout(met)
        self.plot=plot_widget("Tensão no ADC (V)","Tempo de bancada","s");v.addWidget(self.plot,1)
        self.legend=label("CH0 azul · CH1 lilás · CH2 verde · CH3 amarelo · CH4 laranja · CH5 violeta · CH6 verde claro · CH7 rosa. Cada ponto resume 64 conversões; canais sequenciais.","muted",True);v.addWidget(self.legend)
        self.stats=table(["Canal","Última V","Média ADC","Min. ADC¹","Máx. ADC¹","σ STAT²","Média V³","σ V³"]);self.stats.setMinimumHeight(130);self.stats.setMaximumHeight(155);v.addWidget(self.stats)
        row=QHBoxLayout();self.start=QPushButton("Iniciar leitura");self.start.setObjectName("primary");self.stop=QPushButton("Encerrar / salvar");self.stop.setEnabled(False)
        row.addWidget(self.start);row.addWidget(self.stop)
        record=QPushButton("Marcar ponto");record.clicked.connect(lambda:app.guard(self.mark));row.addWidget(record)
        out=QPushButton("Exportar CSV");out.clicked.connect(lambda:app.guard(self.export));row.addWidget(out)
        report=QPushButton("Relatório");report.clicked.connect(lambda:app.guard(self.report));row.addWidget(report);row.addStretch();v.addLayout(row)
        self.start.clicked.connect(lambda:app.guard(self.begin));self.stop.clicked.connect(self.end)
        self.status=label("¹ Extremos recebidos em STAT. ² Desvio das 64 leituras, quando o firmware oferece. ³ Estatística das médias STAT ao longo do tempo, por canal.","muted",True);v.addWidget(self.status)
        gains=QWidget();g=QVBoxLayout(gains);self.tabs.addTab(gains,"CD4066 · controle manual")
        g.addWidget(label("Teste o CD4066 separado antes de ligá-lo ao TIA.","heading",True))
        g.addWidget(label("No circuito B: VDD do CD4066 em 3,3 V. Controle 13←GPIO32; 5←GPIO33; 6←GPIO26. R base de 470 kΩ sempre conectado. O firmware desliga todos os ramos antes de ligar outro. Ao reiniciar, controles ficam como entrada e os pull-downs mantêm as chaves abertas.","muted",True))
        self.hw=QCheckBox("Circuito B montado com CD4066 a 3,3 V e pull-downs de 100 kΩ");g.addWidget(self.hw)
        self.gain_combo=combo(RANGE_NAMES);self.settle=spin(50,20,2000,0," ms")
        f=QFormLayout();f.addRow("Faixa",self.gain_combo);f.addRow("Espera após a troca",self.settle);g.addLayout(f)
        line=QHBoxLayout()
        for title,cmd in (("Ativar chaves","enable"),("Aplicar faixa","set"),("Consultar estado","query"),("Desativar controles","disable")):
            b=QPushButton(title);b.clicked.connect(lambda checked=False,c=cmd:app.guard(lambda:self.gain_command(c)));line.addWidget(b)
        g.addLayout(line)
        self.gain_state=QPlainTextEdit();self.gain_state.setReadOnly(True);g.addWidget(self.gain_state,1)
        g.addWidget(label("Os valores das faixas são ideais. RON, fuga e parasitas precisam ser medidos. Não avance para automático se uma faixa oscila, satura ou demora a estabilizar. O MCP3208 a 20 kS/s não exclui oscilação acima de Nyquist: para validar estabilidade, use osciloscópio.","muted",True))
        fast=QWidget();fv=QVBoxLayout(fast);self.tabs.addTab(fast,"Sinal bruto / ruído")
        fv.addWidget(label("Captura rápida sem estímulo no monitor","heading",True))
        fv.addWidget(label("Use em um ponto DC estável para comparar ruído, ganho e montagem. Usa o CAP binário real, com cada timestamp e código preservados. As condições eletrônicas são copiadas da aba Medições; confira-as antes de capturar.","muted",True))
        line=QHBoxLayout();self.fast_channel=spin(0,0,7);self.fast_rate=combo([5000,10000,20000],10000);self.fast_window=spin(300,40,600,1," ms")
        for text,widget in (("Canal",self.fast_channel),("Taxa S/s",self.fast_rate),("Janela",self.fast_window)):
            line.addWidget(label(text));line.addWidget(widget)
        self.fast_button=QPushButton("Capturar e salvar bruto");self.fast_button.clicked.connect(lambda:app.guard(self.snapshot));line.addWidget(self.fast_button);fv.addLayout(line)
        self.fast_plot=plot_widget();fv.addWidget(self.fast_plot,1)
        self.spectrum_plot=plot_widget("Amplitude exploratória (códigos)","Frequência","Hz");fv.addWidget(self.spectrum_plot,1)
        self.fast_stats=label("Nenhuma captura rápida ainda.","muted",True);fv.addWidget(self.fast_stats)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.cycle)
        app.device.result.connect(self.received);app.device.error.connect(self.failed)

    def begin(self):
        if self.snapshot_pending:raise ValueError("Aguarde a captura rápida terminar.")
        if self.app.acquisition.running:raise ValueError("Encerre o ensaio de monitor antes de usar a bancada.")
        if not self.app.device.connected:raise ValueError("Conecte o ESP32 na página Início.")
        chosen=[i for i,w in enumerate(self.channels) if w.isChecked()]
        if not chosen:raise ValueError("Escolha pelo menos um canal.")
        if self.source.currentText()=="INTERNO" and chosen!=[0]:raise ValueError("ADC interno: marque somente CH0; ligação física em GPIO34.")
        cfg=dict(title=self.title.text(),channels=chosen,vref=self.vref.value(),adc=self.source.currentText(),
                 interval_ms=self.interval.value(),channel_roles="CH0 entrada, CH1 saída A, CH2 saída B somente se montado assim")
        self.sid=self.app.store.session(self.title.text() or "Bancada",cfg,kind="bancada",provenance={"hello":self.app.device.hello})
        self.running=True;self.stopping=False;self.start.setEnabled(False);self.stop.setEnabled(True)
        self.started=time.monotonic();self.data=[];self.latest={}
        self.vref.setEnabled(False);self.source.setEnabled(False);self.title.setEnabled(False)
        for w in self.channels:w.setEnabled(False)
        self.chosen=chosen;self.cycle();self.app.busy_changed()

    def cycle(self):
        if not self.running:return
        if self.stopping:return self.finish()
        self.cycle_start=time.monotonic();self.todo=list(self.chosen);self.next_channel()

    def next_channel(self):
        if not self.running:return
        if self.stopping:return self.finish()
        if not self.todo:
            self.draw();elapsed=(time.monotonic()-self.cycle_start)*1000
            self.timer.start(max(1,round(self.interval.value()-elapsed)));return
        self.current_channel=self.todo.pop(0)
        self.pending=self.app.device.submit("stat",dict(source=self.source.currentText(),channel=self.current_channel))

    def received(self,ident,kind,result):
        callback=self.callbacks.pop(ident,None)
        if callback:
            if kind=="command":
                self.gain_state.setPlainText(json.dumps(result,indent=2,ensure_ascii=False))
                if self.sid:self.app.store.event(self.sid,"gain_bancada",result)
            try:callback(result)
            except Exception as exc:
                if self.snapshot_pending:
                    self.app.store.failure(self.snapshot_sid,str(exc),getattr(exc,"wire",b""));self.snapshot_done("falha")
                self.app.log_exception(exc);self.app.notify(str(exc))
        if ident!=self.pending:return
        self.pending=None
        try:
            elapsed=time.monotonic()-self.started;ch=self.current_channel
            voltage=self.app.store.bench_add(self.sid,elapsed,ch,result,self.vref.value())
            item=dict(elapsed_s=elapsed,channel=ch,mean_raw=result["mean_raw"],min_raw=result.get("min_raw"),max_raw=result.get("max_raw"),
                      std_raw=result.get("std_raw"),vref=self.vref.value(),value_v=voltage,payload=json.dumps(result,ensure_ascii=False))
            self.latest[ch]=item;self.data.append(item)
            self.voltage.set(fmt(voltage,5," V"),f"CH{ch} · VREF informada {self.vref.value():.4f} V")
            self.codes.set(fmt(result["mean_raw"],3),"Pacote recebido com todos os códigos zero" if result["mean_raw"]==0 else "Sem conversão calibrada para o ADC interno" if voltage is None else "12 bits · divisão por 4096")
            if result.get("max_raw",0)>=4093:self.status.setText("Limite alto atingido: a leitura pode estar saturada. Reduza o sinal; não conclua que a saída vale exatamente VREF.")
            elif result["mean_raw"]==0:self.status.setText("Leitura zero recebida. Pode ser válida no GND; não confirma por si só o funcionamento de referência, SPI ou circuito.")
            else:self.status.setText("Dados sendo salvos automaticamente. Canais sequenciais; a curva mostra médias de 64 leituras.")
            self.next_channel()
        except Exception as exc:
            self.app.store.failure(self.sid,str(exc));self.finish("falha");self.app.notify(str(exc))

    def draw(self,*_):
        self.plot.clear();raw=self.raw.isChecked()
        self.plot.setLabel("left","Código ADC (média STAT)" if raw else "Tensão no ADC (V)")
        for ch in sorted({r["channel"] for r in self.data}):
            rows=[r for r in self.data if r["channel"]==ch]
            end=self.data[-1]["elapsed_s"] if self.data else 0
            rows=[r for r in rows if r["elapsed_s"]>=end-60]
            vals=[r["mean_raw"] if raw else r["value_v"] for r in rows]
            if vals and all(v is not None for v in vals):
                self.plot.plot([r["elapsed_s"] for r in rows],vals,pen=pg.mkPen(COLORS[ch],width=1.7),symbol="o",symbolSize=3,symbolBrush=COLORS[ch])
        rows=[]
        for ch,last in sorted(self.latest.items()):
            group=[r for r in self.data if r["channel"]==ch]
            vals=[r["value_v"] for r in group if r["value_v"] is not None]
            mins=[r["min_raw"] for r in group if r["min_raw"] is not None];maxs=[r["max_raw"] for r in group if r["max_raw"] is not None]
            rows.append([f"CH{ch}",fmt(last["value_v"],5),fmt(last["mean_raw"],3),fmt(min(mins) if mins else None,0),
                         fmt(max(maxs) if maxs else None,0),fmt(last["std_raw"],3),fmt(np.mean(vals) if vals else None,5),fmt(np.std(vals,ddof=1) if len(vals)>1 else None,6)])
        fill_table(self.stats,rows)
        if (0 in self.latest and 1 in self.latest and self.latest[0]["value_v"] is not None and self.latest[1]["value_v"] is not None
                and abs(self.latest[0]["elapsed_s"]-self.latest[1]["elapsed_s"])<=2):
            d=(self.latest[1]["value_v"]-self.latest[0]["value_v"])*1000
            db=(self.latest[2]["value_v"]-self.latest[0]["value_v"])*1000 if 2 in self.latest and self.latest[2]["value_v"] is not None else None
            self.delta.set(fmt(d,3," mV"),"Saída B − entrada: "+fmt(db,3," mV")+" · sequenciais")
        else:self.delta.set("N/D","Canais de entrada/saída não disponíveis no mesmo intervalo.")

    def end(self):
        self.stopping=True;self.timer.stop();self.status.setText("Encerrando após a leitura pendente…")
        if self.pending is None:self.finish()

    def finish(self,status="concluida"):
        if not self.running:return
        self.running=False;self.timer.stop();self.pending=None
        self.app.store.finish(self.sid,status);self.start.setEnabled(True);self.stop.setEnabled(False)
        self.vref.setEnabled(True);self.source.setEnabled(True);self.title.setEnabled(True)
        for w in self.channels:w.setEnabled(True)
        self.draw();self.app.refresh_history();self.app.busy_changed()

    def failed(self,ident,kind,error):
        if ident in self.callbacks:self.callbacks.pop(ident)
        if self.running:
            self.app.store.failure(self.sid,error["message"],error.get("wire",b""));self.finish("falha")
        if self.snapshot_pending:
            self.app.store.failure(self.snapshot_sid,error["message"],error.get("wire",b""));self.snapshot_done("falha")

    def mark(self):
        if not self.sid or not self.latest:raise ValueError("Inicie a bancada e aguarde uma leitura.")
        text,ok=QInputDialog.getText(self,"Marcar ponto","Nome da condição / ponto do circuito",text=self.title.text())
        if not ok:return
        self.app.store.event(self.sid,"ponto_marcado",dict(label=text,readings=self.latest))
        self.app.notify("Ponto marcado com as últimas leituras e seus canais.")

    def export(self):
        if not self.sid:raise ValueError("Ainda não há sessão de bancada.")
        if self.app.store.rows(self.sid):
            folder=QFileDialog.getExistingDirectory(self,"Pasta para exportar todas as amostras de bancada")
            if folder:export_csv(self.app.store,self.sid,folder);self.app.notify("Amostras brutas e metadados exportados.")
            return
        path,_=QFileDialog.getSaveFileName(self,"CSV de bancada","bancada_iris.csv","CSV (*.csv)")
        if path:write_csv(path,self.app.store.bench_rows(self.sid));self.app.notify("CSV salvo: "+path)

    def report(self):
        if not self.sid:raise ValueError("Ainda não há sessão de bancada.")
        if self.running:raise ValueError("Encerre a bancada antes de gerar relatório.")
        folder=QFileDialog.getExistingDirectory(self,"Pasta do relatório de bancada")
        if folder:
            path=report_html(self.app.store,self.sid,folder);report_pdf(path,Path(folder)/"relatorio.pdf");self.app.notify("Relatório de bancada salvo.")

    def gain_command(self,kind):
        if self.app.acquisition.running or self.snapshot_pending:raise ValueError("O ganho está sob controle da captura. Encerre-a antes do controle manual.")
        if not self.app.device.connected:raise ValueError("Conecte o ESP32.")
        if "gain4" not in self.app.device.hello.get("features",[]):raise ValueError("Atualize o firmware para v4.1.0; ganho fixo funciona sem a atualização.")
        if kind in ("enable","set") and not self.hw.isChecked():raise ValueError("Confira a montagem descrita e marque a identificação do Circuito B.")
        if kind=="enable":
            ident=self.app.device.command(f"GAIN SETTLE {self.settle.value()}")
            self.callbacks[ident]=lambda _ : self._gain_enable()
        else:
            cmd={"set":f"GAIN SET {self.gain_combo.currentIndex()}","query":"GAIN?","disable":"GAIN ENABLE 0"}[kind]
            ident=self.app.device.command(cmd);self.callbacks[ident]=lambda _:None

    def _gain_enable(self):
        ident=self.app.device.command("GAIN ENABLE 1");self.callbacks[ident]=lambda _:None

    def open_session(self,sid):
        if self.running or self.snapshot_pending:raise ValueError("Encerre a bancada antes de abrir outra sessão.")
        self.sid=sid;session=self.app.store.get_session(sid);self.title.setText(session["title"])
        self.data=self.app.store.bench_rows(sid);self.latest={}
        self.vref.setValue(session["config"].get("vref",self.data[0]["vref"] if self.data else 3.3))
        self.source.setCurrentText(session["config"].get("adc","MCP3208"))
        for r in self.data:self.latest[r["channel"]]=r
        self.voltage.set("—","Sessão histórica; consulte a tabela por canal.")
        self.codes.set("—","Sem aquisição em execução.")
        self.draw();self.status.setText("Sessão histórica aberta; nenhuma aquisição em execução.")
        captures=self.app.store.rows(sid)
        if captures:
            self.show_snapshot(self.app.store.capture(captures[-1]["capture_id"]))

    def snapshot(self):
        if self.running or self.snapshot_pending or self.app.acquisition.running:raise ValueError("Encerre a aquisição atual antes da captura rápida.")
        if not self.app.device.connected:raise ValueError("Conecte o ESP32.")
        from ..core.protocolo import validar_configuracao
        source=self.source.currentText();channel=self.fast_channel.value();period=1000000//int(self.fast_rate.currentText())
        validar_configuracao(source,period,self.fast_window.value(),channel,1000000)
        cfg=self.app.measure.config(technical=True).to_dict();cfg.update(title=self.title.text()+" · sinal bruto",adc=source,channel=channel,
            vref=self.vref.value(),rate_sps=int(self.fast_rate.currentText()),window_ms=self.fast_window.value())
        self.snapshot_sid=self.app.store.session(cfg["title"],cfg,kind="bancada",provenance={"hello":self.app.device.hello})
        self.snapshot_pending=True;self.fast_button.setEnabled(False);self.app.busy_changed()
        ident=self.app.device.submit("configure",dict(fonte=source,periodo_us=period,janela_ms=self.fast_window.value(),canal=channel,spi_hz=1000000))
        self.callbacks[ident]=self.snapshot_configured

    def snapshot_configured(self,_):
        ident=self.app.device.submit("capture",{"bench_snapshot":True})
        self.callbacks[ident]=self.snapshot_received

    def snapshot_received(self,cap):
        task=dict(origin=0,destination=0,repetition=1,phase="sinal_bancada")
        cid=self.app.store.save_capture(self.snapshot_sid,cap,task)
        self.app.store.save_analysis(cid,analyze(cap,0,0))
        self.show_snapshot(cap);self.snapshot_done("concluida")

    def show_snapshot(self,cap):
        st=estatisticas(cap);t=(cap.t_us-cap.t_us[0])/1000
        self.fast_plot.clear();self.fast_plot.plot(t,cap.adc,pen=pg.mkPen(COLORS[0],width=1))
        self.spectrum_plot.clear();spectrum=espectro(cap)
        if spectrum is not None:self.spectrum_plot.plot(*spectrum,pen=pg.mkPen(COLORS[1],width=1))
        self.fast_stats.setText(f"{st['n']} amostras · média {st['media']:.3f} · σ {st['desvio_padrao']:.3f} cód. · pp {st['pico_a_pico']:.0f} cód. · rail {st['fracao_rail']*100:.2f}% · temporização {'regular no critério' if st['temporizacao_valida'] else 'revisar'}. FFT exploratória {'disponível' if spectrum is not None else 'bloqueada por irregularidade'}. Não exclui oscilação além da banda amostrada.")

    def snapshot_done(self,status):
        self.app.store.finish(self.snapshot_sid,status);self.sid=self.snapshot_sid
        self.snapshot_pending=False;self.fast_button.setEnabled(True);self.app.refresh_history();self.app.busy_changed()
        self.app.notify("Captura rápida salva: "+status)
