import json
from pathlib import Path
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QCheckBox,
    QPushButton,QTabWidget,QFileDialog,QSplitter,QLineEdit,QSizePolicy)
from .widgets import label,combo,table,fill_table,plot_widget,COLORS,fmt
from ..analysis import curve,plateau_stats,summary
from ..config import comparison_conditions
from ..exports import write_csv


class ComparePage(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.export_rows=[]
        layout=QVBoxLayout(self);layout.addWidget(label("Compare condições, curvas e aquisição","heading"))
        self.selectors=[];self.source_filters=[];grid=QGridLayout()
        for i in range(2):
            cb=QComboBox();self.selectors.append(cb);grid.addWidget(label("Condição "+("A" if i==0 else "B")),i,0);grid.addWidget(cb,i,1)
            cb.currentIndexChanged.connect(self.select_sessions)
            source=combo(["Todas as fontes"]);source.setToolTip("Filtrar pelo ADC realmente registrado em cada captura, inclusive ensaios antigos com ambas as fontes.")
            self.source_filters.append(source);grid.addWidget(source,i,4);source.currentTextChanged.connect(self.draw)
        self.variable=combo(["ADC","Amplificador","Rf","Cf","Alimentação","Overdrive","Autoranging","Monitor","Exploratória"])
        grid.addWidget(label("Variável investigada"),0,2);grid.addWidget(self.variable,0,3)
        self.pair=QComboBox();grid.addWidget(label("Transição"),1,2);grid.addWidget(self.pair,1,3)
        self.variable.currentTextChanged.connect(self.draw);self.pair.currentIndexChanged.connect(self.draw);layout.addLayout(grid)
        more=QHBoxLayout();more.addWidget(label("Outros pares para sobrepor (opcional)"));self.extra_pairs=QLineEdit();self.extra_pairs.setPlaceholderText("51>102, 102>204");more.addWidget(self.extra_pairs,1);layout.addLayout(more);self.extra_pairs.editingFinished.connect(self.draw)
        more.addWidget(label("Taxa"));self.rate_filter=QComboBox();self.rate_filter.addItem("Todas as taxas",None);more.addWidget(self.rate_filter);self.rate_filter.currentIndexChanged.connect(self.draw)
        self.warning=label("Escolha duas sessões. Nenhuma causa é atribuída automaticamente.","muted",True);layout.addWidget(self.warning)
        options=QGridLayout();self.unit=combo(["%","ADC","V"]);options.addWidget(label("Eixo"),0,0);options.addWidget(self.unit,0,1)
        self.align=QCheckBox("Alinhar em t10 (não comparar latência)");self.align.setChecked(False);options.addWidget(self.align,0,2)
        self.processed=QCheckBox("Curvas processadas");options.addWidget(self.processed,1,0,1,2)
        self.all_reps=QCheckBox("Todas as repetições do par");options.addWidget(self.all_reps,1,2)
        update=QPushButton("Atualizar sessões");update.clicked.connect(self.refresh);options.addWidget(update,0,3,2,1);layout.addLayout(options)
        self.unit.currentTextChanged.connect(self.draw)
        for w in (self.align,self.processed,self.all_reps):w.toggled.connect(self.draw)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.tabs.setMinimumHeight(300)
        self.tabs.setMaximumHeight(400)
        self.overlay=plot_widget();self.tabs.addTab(self.overlay,"Sobreposição")
        self.overlay.setMinimumHeight(250)
        side=QWidget();h=QHBoxLayout(side);self.side=[plot_widget(),plot_widget()]
        for p in self.side:h.addWidget(p)
        self.side[1].setXLink(self.side[0]);self.side[1].setYLink(self.side[0]);self.tabs.addTab(side,"Lado a lado · eixos ligados")
        self.bench_table=table(["Condição / canal","Registros","Média V","σ das médias V","σ médio STAT (cód.)","Min. ADC","Máx. ADC"])
        self.tabs.addTab(self.bench_table,"Bancada / seguidor")
        self.legend=label("Azul: condição A · lilás: condição B. Todas as repetições usam transparência. Os valores no gráfico dependem da unidade e do alinhamento escolhidos.","muted",True);layout.addWidget(self.legend)
        self.metrics=table(["Condição","Rep.","G2G ms","Pico %","σ patamar cód.","Ruído / amplitude %","pp patamar cód.","Rail %","Taxa real S/s","Faixa"])
        self.metrics.setMinimumHeight(130);self.metrics.setMaximumHeight(180);layout.addWidget(self.metrics)
        self.interpretation=label("","muted",True);layout.addWidget(self.interpretation)
        b=QPushButton("Exportar indicadores CSV");b.clicked.connect(lambda:app.guard(self.export));layout.addWidget(b)
        self.setMinimumHeight(810)

    def refresh(self):
        current=[cb.currentData() for cb in self.selectors]
        sessions=self.app.store.sessions()
        for index,cb in enumerate(self.selectors):
            cb.blockSignals(True);cb.clear();cb.addItem("Selecione…",None)
            for s in sessions:cb.addItem(("[SIM] " if s["simulation"] else "")+s["title"]+" · "+s["created"][:16],s["id"])
            i=cb.findData(current[index]);cb.setCurrentIndex(i if i>=0 else 0);cb.blockSignals(False)
        self.select_sessions()

    def select_sessions(self,*_):
        self.sessions=[];self.rows=[]
        for cb in self.selectors:
            sid=cb.currentData()
            session=self.app.store.get_session(sid) if sid else None
            self.sessions.append(session)
            self.rows.append(self.app.store.rows(sid,include_pilots=session["kind"]=="bancada") if sid else [])
        for index,source in enumerate(self.source_filters):
            current=source.currentText();source.blockSignals(True);source.clear();source.addItem("Todas as fontes")
            source.addItems(sorted({r["meta"].get("source","Não informada") for r in self.rows[index]}))
            pos=source.findText(current);source.setCurrentIndex(max(0,pos));source.blockSignals(False)
        rate=self.rate_filter.currentData();self.rate_filter.blockSignals(True);self.rate_filter.clear();self.rate_filter.addItem("Todas as taxas",None)
        periods=sorted({r["meta"].get("period_us") for rows in self.rows for r in rows if r["meta"].get("period_us")})
        for period in periods:self.rate_filter.addItem(f"{1000000/period:g} S/s",period)
        idx=self.rate_filter.findData(rate);self.rate_filter.setCurrentIndex(max(0,idx));self.rate_filter.blockSignals(False)
        pairs=sorted(set((r["origem_rgb"],r["destino_rgb"]) for rows in self.rows for r in rows))
        self.pair.blockSignals(True);self.pair.clear()
        for a,b in pairs:self.pair.addItem(f"{a} → {b}",(a,b))
        self.pair.blockSignals(False);self.draw()

    def draw(self,*_):
        if not hasattr(self,"sessions"):return
        for p in [self.overlay,*self.side]:p.clear()
        if not all(self.sessions):return
        a,b=self.sessions
        differences,unknown=comparison_conditions(a["config"],b["config"],self.variable.currentText())
        text="Variável investigada: "+self.variable.currentText()+". "
        if a["id"]==b["id"]:text+="Mesma sessão; confira os filtros de fonte e taxa de cada lado. "
        if differences:text+="Também diferem: "+", ".join(differences)+". Comparação não isola uma causa. "
        if unknown:text+="Informações ausentes: "+", ".join(unknown)+". "
        if a["simulation"] or b["simulation"]:text+="Inclui SIMULAÇÃO; não usar para conclusão de bancada. "
        if not differences and not unknown:text+="Condições declaradas coincidem; ainda é necessário verificar montagem, ordem e repetibilidade."
        self.warning.setText(text)
        self.draw_bench()
        pair=self.pair.currentData();self.export_rows=[];table_rows=[]
        if not pair:fill_table(self.metrics,[]);return
        pairs=[pair]
        if self.extra_pairs.text().strip():
            try:
                from ..config import TestConfig
                pairs+=TestConfig(custom_pairs=self.extra_pairs.text()).pairs()
            except ValueError as exc:self.warning.setText(text+" "+str(exc));return
        filtered=[];groups=[]
        for index,rows in enumerate(self.rows):
            selected=self.source_filters[index].currentText()
            subset=[r for r in rows if selected=="Todas as fontes" or r["meta"].get("source")==selected]
            if self.rate_filter.currentData() is not None:subset=[r for r in subset if r["meta"].get("period_us")==self.rate_filter.currentData()]
            filtered.append(subset)
            group=[r for r in subset if (r["origem_rgb"],r["destino_rgb"]) in pairs]
            if not self.all_reps.isChecked():
                first={}
                for r in group:first.setdefault((r["origem_rgb"],r["destino_rgb"],r["meta"].get("source")),r)
                group=list(first.values())
            groups.append(group)
        unit=self.unit.currentText()
        actual=[{(r["meta"].get("gain_enabled",False),r["meta"].get("gain_range") if r["meta"].get("gain_enabled") else "fixo") for r in group} for group in groups]
        if actual[0]!=actual[1]:
            text+=" As faixas registradas nas capturas também diferem; compare a banda e os offsets de cada faixa. "
            self.warning.setText(text)
        if (unit=="%" and any(not r.get("amplitude_adc") for g in groups for r in g)) or (unit=="V" and (any(r["meta"].get("source")=="INTERNO" for g in groups for r in g) or any(s["config"].get("vref") is None for s in self.sessions))):
            unit="ADC";self.warning.setText(text+" Eixo de ambas as condições em códigos ADC: normalização ou calibração em volts indisponível. Leituras inválidas continuam visíveis.")
        for index,(s,group) in enumerate(zip(self.sessions,groups)):
            for r in group:
                try:
                    cap=self.app.store.capture(r["capture_id"])
                    t,raw,processed=curve(cap,r,unit=unit,vref=s["config"].get("vref",3.3),align=self.align.isChecked())
                    y=processed if self.processed.isChecked() else raw
                    styles=[Qt.PenStyle.SolidLine,Qt.PenStyle.DashLine,Qt.PenStyle.DotLine,Qt.PenStyle.DashDotLine]
                    actual_pair=(r["origem_rgb"],r["destino_rgb"])
                    pen=pg.mkPen(COLORS[index],width=1.5,style=styles[pairs.index(actual_pair)%4])
                    self.overlay.plot(t,y,pen=pen);self.side[index].plot(t,y,pen=pen)
                    for p in (self.overlay,self.side[index]):
                        p.setLabel("left",{"%":"Resposta relativa (%)","ADC":"Código ADC","V":"Tensão ADC (V)"}[unit])
                        p.setLabel("bottom","Tempo desde t10 (ms)" if self.align.isChecked() else "Tempo desde início (ms)")
                    st=plateau_stats(cap,r,s["config"].get("vref",3.3))
                    row=dict(condition=("A" if index==0 else "B")+" · "+cap.meta.get("source","?"),session_id=s["id"],capture_id=r["capture_id"],
                        repetition=r["repetition"],origin=r["origem_rgb"],destination=r["destino_rgb"],valid=bool(r.get("valida")),
                        g2g_ms=r.get("g2g_ms") if r.get("valida") else None,peak_pct=r.get("overshoot_pct") if r.get("valida") else None,
                        **st,rate_sps=r.get("estatisticas",{}).get("taxa_media_sps"),
                        gain_range=cap.meta.get("gain_range") if cap.meta.get("gain_enabled") else "fixo",differences=differences,unknown=unknown)
                    self.export_rows.append(row)
                    table_rows.append([row["condition"]+f" {row['origin']}→{row['destination']}",row["repetition"],fmt(row["g2g_ms"]),fmt(row["peak_pct"],2),fmt(st.get("sigma_adc"),3),
                        fmt(st.get("noise_relative_pct"),3),fmt(st.get("pp_adc"),1),fmt(st.get("rail_pct"),2),fmt(row["rate_sps"],0),row["gain_range"]])
                except Exception as exc:
                    text+=" Curva indisponível: "+str(exc);self.warning.setText(text)
        fill_table(self.metrics,table_rows)
        style_names=["contínua","tracejada","pontilhada","traço/ponto"]
        self.legend.setText("A: azul · B: lilás. Pares: "+"; ".join(f"{a}→{b} {style_names[i%4]}" for i,(a,b) in enumerate(pairs))+". Repetições do mesmo par mantêm estilo; valores individuais na tabela.")
        valid_counts=[]
        for s,rows in zip(self.sessions,filtered):
            n=len([r for r in rows if r.get("valida")]);valid_counts.append(f"{n}/{len(rows)}")
        self.interpretation.setText(f"Capturas aceitas no algoritmo: A {valid_counts[0]} · B {valid_counts[1]}. Compare ruído em patamares equivalentes, mesma taxa e mesma faixa útil. Atraso aparente pode vir do estímulo, montagem ou temporização; este gráfico não mede input lag. Alinhar em t10 remove a diferença de posição temporal.")

    def draw_bench(self):
        rows=[]
        for i,s in enumerate(self.sessions):
            data=self.app.store.bench_rows(s["id"])
            for ch in sorted({r["channel"] for r in data}):
                group=[r for r in data if r["channel"]==ch]
                vals=[r["value_v"] for r in group if r["value_v"] is not None]
                sigma=[r["std_raw"] for r in group if r["std_raw"] is not None]
                mins=[r["min_raw"] for r in group if r["min_raw"] is not None];maxs=[r["max_raw"] for r in group if r["max_raw"] is not None]
                rows.append([f"{'A' if i==0 else 'B'} · CH{ch}",len(group),fmt(np.mean(vals) if vals else None,5),
                    fmt(np.std(vals,ddof=1) if len(vals)>1 else None,6),fmt(np.mean(sigma) if sigma else None,3),min(mins) if mins else None,max(maxs) if maxs else None])
        fill_table(self.bench_table,rows)

    def export(self):
        if not self.export_rows:raise ValueError("Selecione duas sessões e um par com curvas.")
        path,_=QFileDialog.getSaveFileName(self,"Indicadores comparativos","comparacao_iris.csv","CSV (*.csv)")
        if path:write_csv(path,self.export_rows);self.app.notify("Indicadores e condições exportados.")
