from dataclasses import asdict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,
    QLineEdit,QPlainTextEdit,QCheckBox,QPushButton,QProgressBar,QApplication)
from .widgets import label,spin,combo,scroll
from ..config import TestConfig
from ..core.nucleo import Criterios
from ..acquisition import progress_text


STANDARD_FIELDS = {
    "title","monitor","overdrive","brightness","contrast","resolution","refresh_hz","warmup_min",
    "hdr","vrr","sensor_position","ambient","levels","repetitions","custom_pairs","screen","notes",
}


class MeasurePage(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app
        layout=QVBoxLayout(self)
        self.advanced=False
        layout.addWidget(label("Identifique o monitor e escolha as transições.","muted",True))
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.fields={};cfg=TestConfig.from_dict(app.store.setting("last_config",{}))
        # Atualiza apenas o conjunto padrão antigo; ajustes personalizados ficam intactos.
        old_defaults = {**asdict(Criterios()), "amplitude_minima":20.0}
        if cfg.criteria == old_defaults:
            cfg.criteria = asdict(Criterios())
        def page(name):
            w=QWidget();form=QFormLayout(w);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft);form.setVerticalSpacing(11)
            self.tabs.addTab(scroll(w),name);return form
        def add(form,key,text,widget):
            form.addRow(text,widget);self.fields[key]=widget;return widget
        f=page("Monitor")
        self.screen=combo([])
        for screen in QApplication.screens():
            self.screen.addItem(self.screen_description(screen))
        self.screen.setCurrentIndex(min(cfg.screen,self.screen.count()-1))
        detect=QPushButton("Preencher dados da tela")
        detect.clicked.connect(self.fill_display)
        display=QHBoxLayout()
        display.addWidget(self.screen,1);display.addWidget(detect)
        f.addRow("Tela do estímulo",display)
        for key,text in (("title","Nome do ensaio"),("monitor","Monitor / modelo"),("overdrive","Overdrive"),
            ("brightness","Brilho do monitor"),("contrast","Contraste"),("resolution","Resolução")):
            add(f,key,text,QLineEdit(str(getattr(cfg,key))))
        self.fields["monitor"].setPlaceholderText("Fabricante e modelo exato")
        self.fields["overdrive"].setPlaceholderText("Ex.: Fast, Normal ou Configuração única")
        add(f,"refresh_hz","Atualização",spin(cfg.refresh_hz,1,1000,2," Hz"))
        add(f,"warmup_min","Aquecimento já realizado",spin(cfg.warmup_min,0,240,1," min"))
        for key,text,values in (("hdr","HDR",["Não informado","Desligado","Ligado"]),("vrr","VRR",["Não informado","Desligado","Ligado"])):
            add(f,key,text,combo(values,getattr(cfg,key)))
        for key,text in (("sensor_position","Posição / fixação do sensor"),("ambient","Ambiente / luz externa")):
            add(f,key,text,QLineEdit(getattr(cfg,key)))
        self.notes=QPlainTextEdit(cfg.notes);self.notes.setMaximumHeight(85);f.addRow("Notas do ensaio",self.notes)
        plan=page("Plano de teste")
        add(plan,"levels","Níveis de cinza",spin(cfg.levels,2,17))
        add(plan,"repetitions","Repetições por transição",spin(cfg.repetitions,1,100))
        add(plan,"custom_pairs","Pares específicos",QLineEdit(cfg.custom_pairs))
        self.fields["custom_pairs"].setPlaceholderText("0>255, 255>0, 64>192")
        self.plan_label=label("","muted",True);plan.addRow(self.plan_label)
        plan.addRow(label("Deixe os pares em branco para medir a matriz completa.","muted",True))
        f=page("Circuito")
        self.amp=add(f,"amplifier","Amplificador",combo(["MCP6022","MCP6002","LM358","Outro"],cfg.amplifier));self.amp.setEditable(True)
        add(f,"adc","ADC",combo(["MCP3208","INTERNO"],cfg.adc))
        add(f,"channel","Canal MCP3208 / interno = 0",spin(cfg.channel,0,7))
        add(f,"vref","VREF física informada",spin(cfg.vref,.1,3.6,4," V"))
        add(f,"supply_v","Alimentação do amplificador",spin(cfg.supply_v,1.8,5.5,3," V"))
        add(f,"attenuation_k","Atenuação física: V_ADC / V_saida",spin(cfg.attenuation_k,.001,1,4))
        add(f,"rf_kohm","Rf no ganho fixo",spin(cfg.rf_kohm,.1,2000,3," kΩ"))
        add(f,"cf_pf","Cf no ganho fixo",spin(cfg.cf_pf,0,2000,2," pF"))
        add(f,"assembly","Identificação da montagem",QLineEdit(cfg.assembly))
        add(f,"gain_mode","Modo de ganho",combo(["Fixo","Manual CD4066","Automático CD4066"],cfg.gain_mode))
        add(f,"gain_range","Faixa manual G0..G3",spin(cfg.gain_range,0,3))
        self.target=spin(cfg.auto_target*100,50,90,1,"% de VREF");f.addRow("Teto permitido nos pilotos",self.target)
        add(f,"auto_settle_ms","Espera após trocar a faixa",spin(cfg.auto_settle_ms,20,2000,0," ms"))
        f.addRow(label("CD4066: 3,3 V e GPIOs 32/33/26. Os pilotos incluem todos os pares e seus picos; o ganho escolhido fica fixo no ensaio. Valores Rf/Cf do campo fixo não representam as faixas comutadas.","muted",True))
        f.addRow(label("VREF no programa deve corresponder ao pino 15. CH0–CH7: somente 0..VREF, sem tensão negativa ou 5 V diretos. ADC interno: GPIO34; curva em códigos, sem calibração automática em volts.","muted",True))
        f=page("Aquisição")
        add(f,"full_screen","Estímulo em tela cheia",self.check(cfg.full_screen))
        add(f,"patch_percent","Largura e altura do estímulo",spin(cfg.patch_percent,1,100,0,"%"))
        add(f,"background_rgb","Cinza de fundo",spin(cfg.background_rgb,0,255))
        add(f,"rate_sps","Taxa de aquisição",combo([5000,10000,20000],cfg.rate_sps))
        add(f,"window_ms","Janela de captura",spin(cfg.window_ms,40,600,1," ms"))
        add(f,"pre_ms","Pré-estímulo após ARMED",spin(cfg.pre_ms,40,500,0," ms"))
        add(f,"hold_ms","Espera no cinza inicial",spin(cfg.hold_ms,100,60000,0," ms"))
        add(f,"spi_hz","Clock SPI",combo([500000,1000000],cfg.spi_hz))
        add(f,"static_references","Referências estáticas antes / depois",self.check(cfg.static_references))
        add(f,"randomize","Embaralhar transições",self.check(cfg.randomize))
        add(f,"seed","Semente da ordem",spin(cfg.seed,0,2147483647))
        f=page("Processamento")
        self.criteria={}
        for key,text,lo,hi,dec,suf in (
            ("mediana_amostras","Mediana (1 = bruto; ímpares)",1,51,0," amostras"),
            ("patamar_inicial_ms","Janela do patamar inicial",1,150,1," ms"),
            ("patamar_final_ms","Janela do patamar final",1,200,1," ms"),
            ("persistencia_ms","Persistência nos cruzamentos",0,20,2," ms"),
            ("snr_minimo","SNR mínimo",1,1000,1,""),
            ("amplitude_minima","Amplitude mínima",1,4000,1," códigos"),
            ("tolerancia_acomodacao","Faixa relativa de acomodação",.001,.49,3,""),
            ("permanencia_final_ms","Permanência final mínima",1,200,1," ms")):
            widget=spin(cfg.criteria.get(key,getattr(TestConfig().get_criteria(),key)),lo,hi,dec,suf)
            self.criteria[key]=widget;f.addRow(text,widget)
        self.low=QLineEdit("" if cfg.criteria.get("limite_analogico_baixo") is None else str(cfg.criteria["limite_analogico_baixo"]))
        self.high=QLineEdit("" if cfg.criteria.get("limite_analogico_alto") is None else str(cfg.criteria["limite_analogico_alto"]))
        f.addRow("Limite analógico inferior (códigos; opcional)",self.low);f.addRow("Limite analógico superior (códigos; opcional)",self.high)
        bar=QHBoxLayout();self.start=QPushButton("Iniciar ensaio");self.start.setObjectName("primary");self.stop=QPushButton("Encerrar");self.stop.setEnabled(False)
        self.start.clicked.connect(lambda:app.guard(self.begin));self.stop.clicked.connect(app.acquisition.cancel)
        bar.addWidget(self.start);bar.addWidget(self.stop);bar.addStretch();layout.addLayout(bar)
        self.progress=QProgressBar();self.progress.setValue(0);layout.addWidget(self.progress)
        self.status=label("Posicione a sonda antes de iniciar. Pressione Esc para encerrar.","muted",True);layout.addWidget(self.status)
        self.live_progress=label("","muted",True)
        layout.addWidget(self.live_progress)
        app.acquisition.progress_detail.connect(lambda data:self.live_progress.setText(progress_text(data)))
        app.acquisition.status.connect(self.status.setText)
        app.acquisition.progress.connect(lambda a,b:(self.progress.setRange(0,b),self.progress.setValue(a)))
        app.acquisition.busy_changed.connect(self.busy)
        for key in ("levels","repetitions","custom_pairs","window_ms","rate_sps","hold_ms","static_references","gain_mode"):
            w=self.fields[key]
            if isinstance(w,QLineEdit):w.textChanged.connect(self.update_plan)
            elif isinstance(w,QCheckBox):w.toggled.connect(self.update_plan)
            elif hasattr(w,"valueChanged"):w.valueChanged.connect(self.update_plan)
            else:w.currentTextChanged.connect(self.update_plan)
        self.update_plan()
        if not cfg.resolution:
            self.fill_display(only_empty=True)

    @staticmethod
    def check(value):
        w=QCheckBox();w.setChecked(value);return w

    @staticmethod
    def screen_description(screen):
        size=screen.size()
        return f"{screen.name() or 'Tela'} · {size.width()} × {size.height()} · {screen.refreshRate():g} Hz"

    def fill_display(self, only_empty=False):
        index=self.screen.currentIndex()
        screens=QApplication.screens()
        if not 0<=index<len(screens):
            return
        screen=screens[index]
        size=screen.size();scale=screen.devicePixelRatio()
        fields={"resolution":f"{round(size.width()*scale)}×{round(size.height()*scale)}"}
        if screen.model():
            model=screen.model().strip()
            manufacturer=screen.manufacturer().strip()
            fields["monitor"]=f"{manufacturer} {model}".strip() if manufacturer and manufacturer.casefold() not in model.casefold() else model
        for key,value in fields.items():
            if not only_empty or not self.fields[key].text().strip():self.fields[key].setText(value)
        if screen.refreshRate()>0:self.fields["refresh_hz"].setValue(screen.refreshRate())

    def set_advanced(self,value):
        self.advanced=value
        for index in range(2,self.tabs.count()):self.tabs.setTabVisible(index,value)
        self.update_plan()

    def config(self, technical=None):
        technical=self.advanced if technical is None else technical
        out={}
        for key,w in self.fields.items():
            if not technical and key not in STANDARD_FIELDS:continue
            if isinstance(w,QCheckBox):value=w.isChecked()
            elif hasattr(w,"value"):value=w.value()
            elif hasattr(w,"currentText"):value=w.currentText()
            else:value=w.text()
            out[key]=value
        if technical:
            for key in ("rate_sps","spi_hz"):out[key]=int(out[key])
            out["criteria"]={key:widget.value() for key,widget in self.criteria.items()}
            out["criteria"].update(
                limite_analogico_baixo=float(self.low.text()) if self.low.text().strip() else None,
                limite_analogico_alto=float(self.high.text()) if self.high.text().strip() else None,
            )
            out.update(auto_target=self.target.value()/100,gain_calibration=self.app.store.setting("gain_calibration",{}))
        out.update(notes=self.notes.toPlainText(),screen=self.screen.currentIndex())
        return TestConfig.from_dict(out)

    def update_plan(self,*_):
        try:
            cfg=self.config();n=len(cfg.pairs())*cfg.repetitions
            self.plan_label.setText(f"{len(cfg.pairs())} pares × {cfg.repetitions} repetições · {n} transições · cerca de {cfg.capture_count()*cfg.capture_seconds()/60:.1f} min")
        except Exception:self.plan_label.setText("Revise os pares e parâmetros.")

    def begin(self):
        if self.app.bench.running or self.app.bench.snapshot_pending:raise ValueError("Encerre a bancada antes de iniciar o monitor.")
        cfg=self.config()
        if not self.advanced and (not cfg.monitor.strip() or not cfg.overdrive.strip()):
            self.tabs.setCurrentIndex(0)
            raise ValueError("Informe o modelo e o overdrive. Se não houver ajuste, informe ‘Configuração única’.")
        cfg.validate()
        # Persist technical controls even after a basic session. Basic sessions always use instrument defaults.
        previous=self.app.store.setting("last_config",{})
        values=cfg.to_dict()
        if not self.advanced:
            values={key:value for key,value in values.items() if key in STANDARD_FIELDS}
        self.app.store.set_setting("last_config",{**previous,**values})
        self.app.acquisition.start(cfg)

    def busy(self,value):
        self.tabs.setEnabled(not value);self.start.setEnabled(not value);self.stop.setEnabled(value)
