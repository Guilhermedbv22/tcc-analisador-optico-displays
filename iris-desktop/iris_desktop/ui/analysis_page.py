from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QSplitter,QTabWidget,
    QCheckBox,QPushButton,QComboBox,QPlainTextEdit,QFileDialog,QInputDialog)
from .widgets import label,table,fill_table,Metric,CurveView,combo,spin,fmt,plot_widget,scroll,COLORS
from ..analysis import summary,analyze,plateau_stats,describe,matrix_values,matrix_text,matrix_text_color
from ..config import TestConfig
from ..exports import export_curve,export_overview,export_heatmap,export_csv,export_native,report_html,report_pdf
from ..core.nucleo import Criterios


class AnalysisPage(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.sid=None;self.rows=[];self.current=None
        layout=QVBoxLayout(self)
        top=QHBoxLayout();top.addWidget(label("Sessão"));self.sessions=QComboBox();top.addWidget(self.sessions,1)
        self.reload=QPushButton("Atualizar");top.addWidget(self.reload);self.reload.clicked.connect(self.refresh_sessions)
        self.reanalyze_button=QPushButton("Reanalisar com critérios atuais");top.addWidget(self.reanalyze_button)
        self.reanalyze_button.setToolTip("Recalcula com os critérios de Medições. Preserva os dados brutos e as revisões anteriores.")
        self.reanalyze_button.clicked.connect(lambda:app.guard(self.reanalyze_current))
        layout.addLayout(top);self.sessions.currentIndexChanged.connect(self.session_changed)
        self.banner=label("Selecione uma sessão no histórico ou inicie uma medição.","muted",True);layout.addWidget(self.banner)
        averages=QHBoxLayout()
        self.average_response=Metric("Tempo de resposta médio")
        self.average_overshoot=Metric("Ultrapassagem média",COLORS[1])
        self.valid_count=Metric("Capturas válidas",COLORS[2])
        for widget in (self.average_response,self.average_overshoot,self.valid_count):averages.addWidget(widget,1)
        layout.addLayout(averages)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        curvepage=QWidget();c=QVBoxLayout(curvepage);c.setContentsMargins(8,8,8,8)
        split=QSplitter();c.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.setContentsMargins(0,0,4,0)
        self.pilots=QCheckBox("Incluir pilotos e referências");lv.addWidget(self.pilots)
        self.pilots.toggled.connect(self.load_rows)
        self.capture_table=table(["RGB / rep.","G2G ms","Estado"]);lv.addWidget(self.capture_table,1)
        self.capture_table.setMinimumWidth(190);self.capture_table.itemSelectionChanged.connect(self.select_capture)
        split.addWidget(left)
        right=QWidget();rv=QVBoxLayout(right);rv.setContentsMargins(6,0,0,0)
        metrics=QGridLayout();self.metrics=[Metric("Resposta 10–90%"),Metric("Excesso no alvo",COLORS[1]),Metric("Acomodação desde t10",COLORS[6])]
        for i,w in enumerate(self.metrics):metrics.addWidget(w,0,i)
        rv.addLayout(metrics)
        self.interpretation=label("Selecione uma transição.","muted",True);rv.addWidget(self.interpretation)
        controls=QGridLayout();self.unit=combo(["%","ADC","V"]);controls.addWidget(label("Eixo"),0,0);controls.addWidget(self.unit,0,1)
        self.options={}
        for i,(key,text,checked) in enumerate((("raw","Bruto",True),("filtered","Processado",True),
            ("plateaus","Partida / alvo",True),("thresholds","10% / 90%",True),
            ("settling","Acomodação",True),("references","Referência de tempo",False),("align","Alinhar em t10",False))):
            w=QCheckBox(text);w.setChecked(checked);self.options[key]=w
            controls.addWidget(w,1+i//4,i%4);w.toggled.connect(self.plot_current)
        self.unit.currentTextChanged.connect(self.plot_current);rv.addLayout(controls)
        zoom=QHBoxLayout();z=QPushButton("Ampliar transição");z.clicked.connect(self.zoom_transition);zoom.addWidget(z)
        z=QPushButton("Ver janela completa");z.clicked.connect(lambda:self.view.plot.enableAutoRange());zoom.addWidget(z);zoom.addStretch();rv.addLayout(zoom)
        self.view=CurveView();rv.addWidget(self.view,1)
        self.evidence=label("","muted",True);rv.addWidget(self.evidence)
        right.setMinimumHeight(650)
        split.addWidget(scroll(right));split.setStretchFactor(1,1);split.setSizes([250,825])
        self.tabs.addTab(curvepage,"Transição")
        self.summary_widget=QWidget();sv=QVBoxLayout(self.summary_widget)
        self.summary_text=label("","muted",True);sv.addWidget(self.summary_text)
        self.summary_chart=plot_widget("G2G (ms)","Índice do par",None);sv.addWidget(self.summary_chart,1)
        self.summary_key=label("Cada ponto = uma repetição válida. Barras = média do par. Ausência de ponto não é zero.","muted",True);sv.addWidget(self.summary_key)
        self.all_results=table(["Par","Rep.","G2G ms","Pico %","Acomodação ms","Estado"]);self.all_results.setMaximumHeight(180);sv.addWidget(self.all_results)
        self.tabs.addTab(self.summary_widget,"Resumo")
        hm=QWidget();hl=QVBoxLayout(hm);hr=QHBoxLayout();hr.addWidget(label("Matriz"));self.metric=QComboBox()
        for name,key in (("Tempo de resposta (ms)","g2g_ms"),("Overshoot / undershoot (%)","overshoot_pct"),("Acomodação (ms)","acomodacao_ms")):self.metric.addItem(name,key)
        hr.addWidget(self.metric);hr.addStretch();hl.addLayout(hr)
        self.heat=plot_widget("Cinza inicial","Cinza final",None);self.heat.getPlotItem().setAspectLocked(True);hl.addWidget(scroll(self.heat),1)
        self.heat_label=label("Número e cor = média das repetições válidas. — = diagonal, não medida ou inválida. Use a rolagem em grades maiores.","muted",True);hl.addWidget(self.heat_label)
        self.metric.currentTextChanged.connect(self.draw_heatmap);self.colorbar=None
        self.tabs.addTab(hm,"Matriz")
        tech=QWidget();tv=QVBoxLayout(tech)
        row=QHBoxLayout();row.addWidget(label("Mediana na reanálise"));self.median=spin(3,1,51);self.median.setSingleStep(2);row.addWidget(self.median)
        self.use_current_criteria=QCheckBox("Usar demais critérios de Medições");row.addWidget(self.use_current_criteria)
        re=QPushButton("Reanalisar sessão");row.addWidget(re);re.clicked.connect(lambda:app.guard(self.reanalyze));tv.addLayout(row)
        tv.addWidget(label("A reanálise cria uma nova revisão; o sinal bruto e resultados anteriores são preservados. Exibir/esconder uma curva não muda os critérios calculados.","muted",True))
        self.technical=QPlainTextEdit();self.technical.setReadOnly(True);tv.addWidget(self.technical,1)
        self.tabs.addTab(tech,"Técnico / reanálise")
        exports=QHBoxLayout()
        self.advanced_exports=[]
        for text,method in (("Curva PNG",self.export_selected),("Imagem de todos os pares",self.export_all),
                            ("CSV",self.export_data),("Sessão ZIP",self.export_session),("Relatório HTML / PDF",self.export_report),("Publicar no site",self.publish_report)):
            b=QPushButton(text);b.clicked.connect(lambda checked=False,m=method:app.guard(m));exports.addWidget(b)
            if text in ("Curva PNG","Imagem de todos os pares","CSV","Sessão ZIP"):self.advanced_exports.append(b)
            if text=="Publicar no site":b.setObjectName("primary")
        layout.addLayout(exports)

    def set_advanced(self,value):
        self.tabs.setTabVisible(3,value)
        for widget in [self.evidence,self.pilots,self.reanalyze_button,*self.advanced_exports]:
            widget.setVisible(value)

    def publish_report(self):
        self.require_session();self.app.navigate(8);self.app.publication.open_session(self.sid)

    def refresh_sessions(self,selected=None):
        current=selected or self.sid
        self.sessions.blockSignals(True);self.sessions.clear()
        self.sessions.addItem("Selecione…",None)
        for s in self.app.store.sessions(kind="monitor"):
            self.sessions.addItem(("[SIMULAÇÃO] " if s["simulation"] else "")+s["title"]+" · "+s["created"][:16],s["id"])
        index=self.sessions.findData(current)
        self.sessions.setCurrentIndex(index if index>=0 else 0);self.sessions.blockSignals(False)
        self.session_changed()

    def open_session(self,sid):
        self.refresh_sessions(sid)

    def session_changed(self,*_):
        self.sid=self.sessions.currentData()
        if not self.sid:
            self.current=None;self.rows=[]
            for widget in (self.average_response,self.average_overshoot,self.valid_count):widget.set("—")
            self.capture_table.setRowCount(0);self.all_results.setRowCount(0)
            self.view.plot.clear();self.heat.clear();self.summary_chart.clear();self.summary_text.clear()
            self.banner.setText("Selecione uma sessão no histórico ou inicie uma medição.")
            return
        self.session=self.app.store.get_session(self.sid)
        config=self.session["config"]
        self.banner.setText(("SIMULAÇÃO · " if self.session["simulation"] else "")+f"{config.get('monitor') or 'Monitor não informado'} · {config.get('overdrive') or 'OD não informado'} · {config.get('adc') or 'ADC não informado'} · {config.get('amplifier') or 'amplificador não identificado'} · {self.session['status']}")
        self.median.setValue(config.get("criteria",{}).get("mediana_amostras",3))
        self.load_rows()

    def load_rows(self,*_):
        if not self.sid:return
        self.rows=self.app.store.rows(self.sid,include_pilots=self.pilots.isChecked())
        data=[];tips=[]
        for r in self.rows:
            data.append([f"{r['origem_rgb']}→{r['destino_rgb']} · {r['repetition']}",fmt(r.get("g2g_ms") if r.get("valida") else None),
                         "Válida" if r.get("valida") else "Estática" if r.get("status")=="ESTATICA" else "Revisar"])
            tips.append(r["phase"]+"\n"+r.get("meaning",""))
        self.capture_table.blockSignals(True);fill_table(self.capture_table,data,tips);self.capture_table.blockSignals(False)
        if self.rows:self.capture_table.selectRow(0)
        else:self.current=None;self.view.plot.clear()
        self.draw_summary();self.draw_heatmap()

    def select_capture(self):
        index=self.capture_table.currentRow()
        if not 0<=index<len(self.rows):return
        self.current=self.rows[index]
        self.app.guard(self.plot_current)

    def plot_options(self):
        preferences=self.app.store.setting("display",{})
        return {**{k:w.isChecked() for k,w in self.options.items()},
                "reference_ms":preferences.get("reference_ms",5.),
                "reference_label":preferences.get("reference_label","Referência do projeto")}

    def plot_current(self,*_):
        if not self.current:return
        r=self.current;cap=self.app.store.capture(r["capture_id"])
        valid=r.get("valida",False)
        self.view.show_curve(cap,r,self.unit.currentText(),self.session["config"].get("vref",3.3),self.plot_options())
        color=self.app.metric_color(r.get("g2g_ms"),"g2g") if valid else "#ffb454"
        self.metrics[0].set(fmt(r.get("g2g_ms") if valid else None,3," ms"),"De 10% a 90% da mudança",color)
        self.metrics[1].title.setText(r.get("peak_name","Excesso no alvo"))
        self.metrics[1].set(fmt(r.get("overshoot_pct") if valid else None,2,"%"),"Relativo à amplitude medida",self.app.metric_color(r.get("overshoot_pct"),"os") if valid else "#ffb454")
        self.metrics[2].set(fmt(r.get("acomodacao_ms") if valid else None,3," ms"),r.get("acomodacao_status","Não avaliada").replace("_"," ").lower())
        text=r.get("meaning", "Sem análise salva: reanalise esta captura.")
        if self.unit.currentText()!=self.view.data[3]:text+=" Eixo em códigos ADC: não há calibração em volts ou amplitude para normalizar."
        self.interpretation.setText(text)
        st=plateau_stats(cap,r,self.session["config"].get("vref",3.3))
        self.evidence.setText(f"Ruído no patamar inicial: σ {fmt(st.get('sigma_adc'),2)} códigos · pico a pico {fmt(st.get('pp_adc'),1)} · {r.get('analysis_version','')} · faixa {cap.meta.get('gain_range','fixa') if cap.meta.get('gain_enabled') else 'fixa'}")
        c=Criterios(**r["criterios"]) if r.get("criterios") else TestConfig.from_dict(self.session["config"]).get_criteria()
        raw=analyze(cap,r["origem_rgb"],r["destino_rgb"],replace(c,mediana_amostras=1))
        details={"resultado_atual":r,"bruto_sem_mediana":raw,
                 "delta_filtro":dict(g2g_ms=r["g2g_ms"]-raw["g2g_ms"] if valid and raw.get("valida") else None,
                                     pico_pp=r["overshoot_pct"]-raw["overshoot_pct"] if valid and raw.get("valida") else None),
                 "diagnostico_patamar":st,"metadados":cap.meta,
                 "revisoes":[{k:v for k,v in rev.items() if k!="result"} for rev in self.app.store.revisions(r["capture_id"])]}
        self.technical.setPlainText(json.dumps(details,ensure_ascii=False,indent=2))

    def zoom_transition(self):
        if not self.current or self.current.get("t10_ms") is None:return
        r=self.current;shift=r["t10_ms"] if self.options["align"].isChecked() else 0
        end=r["t90_ms"]+25
        if r.get("acomodacao_ms") is not None:end=max(end,r["t10_ms"]+r["acomodacao_ms"]+8)
        self.view.plot.setXRange(r["t10_ms"]-6-shift,end-shift,padding=.02)

    def draw_summary(self):
        if not self.sid:return
        rows=self.app.store.rows(self.sid,False);s=summary(rows)
        self.average_response.set(fmt(s["g2g_ms"]["mean"] if s["g2g_ms"] else None,3," ms"),"G2G 10–90% · somente válidas")
        self.average_overshoot.set(fmt(s["overshoot_pct"]["mean"] if s["overshoot_pct"] else None,2,"%"),"Excesso no alvo; inclui undershoot nas descidas")
        self.valid_count.set(f"{s['valid']} / {s['total']}","Pilotos e referências ficam fora das médias")
        text=f"{s['valid']} de {s['total']} capturas válidas. "
        if s["g2g_ms"]:
            text+=f"G2G médio {s['g2g_ms']['mean']:.3f} ms · excesso médio {s['overshoot_pct']['mean']:.2f}% · subidas {fmt(s['subidas'])} ms · descidas {fmt(s['descidas'])} ms. "
            for key,name in (("fastest","Mais rápida"),("slowest","Mais lenta"),("peak","Maior excesso no alvo")):
                r=s[key];val=r["overshoot_pct"] if key=="peak" else r["g2g_ms"]
                text+=f"{name}: {r['origem_rgb']}→{r['destino_rgb']} ({val:.2f}{'%' if key=='peak' else ' ms'}). "
        text+="Compare condições equivalentes. Estas médias não isolam causas nem classificam o monitor."
        self.summary_text.setText(text)
        pairs=sorted({(r["origem_rgb"],r["destino_rgb"]) for r in rows});self.summary_chart.clear()
        for i,pair in enumerate(pairs):
            vals=[r["g2g_ms"] for r in rows if (r["origem_rgb"],r["destino_rgb"])==pair and r.get("valida")]
            if vals:
                self.summary_chart.addItem(pg.BarGraphItem(x=[i+1],height=[np.mean(vals)],width=.6,brush=pg.mkBrush(104,189,255,45),pen=None))
                self.summary_chart.plot([i+1]*len(vals),vals,pen=None,symbol="o",symbolSize=6,symbolBrush=COLORS[0])
        ticks=[(i+1,f"{a}→{b}") for i,(a,b) in enumerate(pairs)]
        self.summary_chart.getAxis("bottom").setTicks([ticks[::max(1,len(ticks)//16)]])
        fill_table(self.all_results,[[f"{r['origem_rgb']}→{r['destino_rgb']}",r["repetition"],fmt(r.get("g2g_ms") if r.get("valida") else None),
            fmt(r.get("overshoot_pct") if r.get("valida") else None,2),fmt(r.get("acomodacao_ms") if r.get("valida") else None),"Válida" if r.get("valida") else "Revisar"] for r in rows])

    def draw_heatmap(self,*_):
        if not self.sid:return
        rows=self.app.store.rows(self.sid,False)
        metric=self.metric.currentData();levels,data=matrix_values(rows,metric)
        self.heat.clear()
        if self.colorbar:
            self.heat.plotItem.layout.removeItem(self.colorbar);self.colorbar.close();self.colorbar=None
        if not levels:return
        self.heat.setMinimumSize(max(500,len(levels)*46+160),max(400,len(levels)*38+120))
        self.heat.showGrid(x=False,y=False)
        self.heat.getViewBox().invertY(True)
        image=pg.ImageItem(data,axisOrder="row-major");self.heat.addItem(image)
        cmap=pg.colormap.get("viridis")
        mx=float(np.nanmax(data)) if np.isfinite(data).any() else 1.
        limit=max(mx,.01)
        name={"g2g_ms":"Tempo de resposta (ms)","overshoot_pct":"Overshoot / undershoot (%)","acomodacao_ms":"Acomodação (ms)"}[metric]
        self.colorbar=pg.ColorBarItem(values=(0,limit),colorMap=cmap,label=name)
        self.colorbar.setImageItem(image,insert_in=self.heat.plotItem)
        self.heat.getAxis("bottom").setTicks([[(i+.5,str(v)) for i,v in enumerate(levels)]])
        self.heat.getAxis("left").setTicks([[(i+.5,str(v)) for i,v in enumerate(levels)]])
        self.heat_labels=[]
        for (i,j),v in np.ndenumerate(data):
            color=matrix_text_color(cmap.map(float(v)/limit,mode="float")) if np.isfinite(v) else "#9eb1cc"
            text=pg.TextItem(matrix_text(v),anchor=(.5,.5),color=color)
            text.setFont(QFont("Segoe UI",8 if len(levels)>8 else 10))
            text.setPos(j+.5,i+.5);self.heat.addItem(text);self.heat_labels.append(text)
        for edge in range(len(levels)+1):
            self.heat.plot([edge,edge],[0,len(levels)],pen=pg.mkPen("#506070",width=.5))
            self.heat.plot([0,len(levels)],[edge,edge],pen=pg.mkPen("#506070",width=.5))
        self.heat.setRange(xRange=(0,len(levels)),yRange=(0,len(levels)),padding=.03)

    def reanalyze_current(self):
        self.use_current_criteria.setChecked(True)
        self.median.setValue(self.app.measure.config().get_criteria().mediana_amostras)
        self.reanalyze()

    def reanalyze(self):
        self.require_session()
        c=self.app.measure.config().get_criteria() if self.use_current_criteria.isChecked() else TestConfig.from_dict(self.session["config"]).get_criteria()
        c=replace(c,mediana_amostras=self.median.value())
        if c.mediana_amostras%2==0:raise ValueError("Use mediana ímpar; 1 = sem filtro.")
        for r in self.app.store.rows(self.sid):
            cap=self.app.store.capture(r["capture_id"])
            self.app.store.save_analysis(r["capture_id"],analyze(cap,r["origem_rgb"],r["destino_rgb"],c))
        self.app.store.event(self.sid,"reanalise",dict(mediana=c.mediana_amostras,criterios_origem="Medições" if self.use_current_criteria.isChecked() else "Sessão"))
        self.load_rows();self.app.notify("Nova revisão salva; aquisições originais preservadas.")

    def require_session(self):
        if self.app.acquisition.running:raise ValueError("Aguarde o fim do ensaio para exportar ou reanalisar.")
        if not self.sid:raise ValueError("Selecione uma sessão.")

    def export_selected(self):
        self.require_session()
        if not self.current:raise ValueError("Selecione uma transição.")
        path,_=QFileDialog.getSaveFileName(self,"Exportar curva","curva_iris.png","PNG (*.png)")
        if path:
            opt=self.plot_options();opt.pop("align",None)
            export_curve(self.app.store.capture(self.current["capture_id"]),self.current,path,self.session["config"].get("vref",3.3),self.unit.currentText(),opt)
            self.app.notify("Curva exportada: "+path)

    def export_all(self):
        self.require_session();path,_=QFileDialog.getSaveFileName(self,"Exportar todos os pares","transicoes_iris.png","PNG (*.png)")
        if path:export_overview(self.app.store,self.sid,path);self.app.notify("Todos os pares exportados: "+path)

    def export_data(self):
        self.require_session();folder=QFileDialog.getExistingDirectory(self,"Pasta de exportação CSV")
        if folder:export_csv(self.app.store,self.sid,folder);self.app.notify("CSV e amostras exportados.")

    def export_session(self):
        self.require_session();path,_=QFileDialog.getSaveFileName(self,"Sessão com dados brutos e revisões","sessao_iris.zip","ZIP (*.zip)")
        if path:export_native(self.app.store,self.sid,path);self.app.notify("Sessão ZIP exportada.")

    def export_report(self):
        self.require_session();folder=QFileDialog.getExistingDirectory(self,"Pasta do relatório")
        if not folder:return
        conclusion,ok=QInputDialog.getMultiLineText(self,"Conclusão do operador","Conclusão e pendências (opcional)")
        if not ok:return
        path=report_html(self.app.store,self.sid,folder,conclusion);report_pdf(path,Path(folder)/"relatorio.pdf")
        self.app.notify("Relatório HTML/PDF, gráficos e CSV exportados: "+folder)
