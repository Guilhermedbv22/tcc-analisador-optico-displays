from pathlib import Path
import json
import os
import sys
import traceback
import zipfile
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QPixmap,QIcon,QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,
    QStackedWidget,QPushButton,QButtonGroup,QComboBox,QCheckBox,QLabel,QLineEdit,QFileDialog,
    QMessageBox,QFormLayout,QApplication,QPlainTextEdit)
from .widgets import STYLE,COLORS,label,card,scroll,table,fill_table,spin,combo
from .measure import MeasurePage
from .analysis_page import AnalysisPage
from .bench import BenchPage
from .compare import ComparePage
from .publication_page import PublicationPage
from .campaign_page import CampaignPage
from ..device import DeviceClient,ports
from .. import __version__
from ..acquisition import Acquisition
from ..importers import import_monitor,import_bench_csv,import_native_session
from ..exports import export_native,export_csv,report_html,report_pdf


class MainWindow(QMainWindow):
    def __init__(self,store):
        super().__init__();self.store=store
        self.base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
        self.assets=Path(__file__).resolve().parents[1]/"assets"
        self.setWindowTitle("Íris Desktop")
        self.setWindowIcon(QIcon(str(self.assets/"icon.png")))
        self.resize(1280,810);self.setMinimumSize(880,620)
        self.setStyleSheet(STYLE)
        self.device=DeviceClient(self);self.acquisition=Acquisition(self.device,store)
        self.device.result.connect(self.device_result);self.device.error.connect(self.device_error)
        self.acquisition.finished.connect(self.acquisition_finished)
        self.acquisition.busy_changed.connect(self.busy_changed)
        outer=QWidget();self.setCentralWidget(outer);layout=QHBoxLayout(outer);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName("sidebar");sidebar.setFixedWidth(186);nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,15,12,12);nav.setSpacing(4)
        brand=QHBoxLayout()
        logo=QLabel()
        pix=QPixmap(str(self.assets/"icon.png"))
        logo.setPixmap(pix.scaled(35,35,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        brand.addWidget(logo);brand.addWidget(label("Íris Desktop","heading"));brand.addStretch()
        nav.addLayout(brand);nav.addSpacing(12)
        self.stack=QStackedWidget();self.nav=[];self.group=QButtonGroup(self);self.group.setExclusive(True)
        names=["Início","Nova medição","Resultados","Comparações","Diagnóstico","Histórico","Configurações","Ferramentas","Publicar","Campanhas"]
        for i,name in enumerate(names):
            button=QPushButton(name);button.setObjectName("navigation");button.setCheckable(True)
            button.clicked.connect(lambda checked=False,index=i:self.navigate(index))
            self.group.addButton(button);self.nav.append(button)
        for index in (0,1,2,5,8,6):nav.addWidget(self.nav[index])
        nav.addSpacing(9)
        self.advanced_caption=label("AVANÇADO","muted")
        nav.addWidget(self.advanced_caption)
        for index in (7,3,4,9):nav.addWidget(self.nav[index])
        nav.addStretch();nav.addWidget(label(__version__,"muted"))
        layout.addWidget(sidebar)
        body=QWidget();bv=QVBoxLayout(body);bv.setContentsMargins(22,16,22,10)
        header=QHBoxLayout();self.page_title=label("Início","title");header.addWidget(self.page_title);header.addStretch()
        self.technical_mode=QCheckBox("Modo avançado");self.technical_mode.setChecked(store.setting("advanced_mode",False));self.technical_mode.toggled.connect(self.toggle_technical);header.addWidget(self.technical_mode)
        self.connection=label("● Desconectado");self.connection.setStyleSheet("color:#ffbd69;padding:8px;");header.addWidget(self.connection)
        bv.addLayout(header);bv.addWidget(self.stack,1);layout.addWidget(body,1)
        self.home=self.home_page();self.measure=MeasurePage(self);self.analysis=AnalysisPage(self)
        self.compare=ComparePage(self);self.bench=BenchPage(self);self.history=self.history_page();self.settings=self.settings_page()
        self.tools=self.tools_page()
        self.publication=PublicationPage(self)
        self.campaign=CampaignPage(self)
        for page in (self.home,self.measure,self.analysis,self.compare,self.bench,self.history,self.settings,self.tools,self.publication,self.campaign):self.stack.addWidget(scroll(page) if page is self.compare else page)
        self.acquisition.session_started.connect(lambda sid:self.notify("Medição iniciada."))
        self.toggle_technical(self.technical_mode.isChecked());self.refresh_ports();self.refresh_history();self.navigate(0)
        self.connecting=False;self._closing=False
        self.statusBar().showMessage("Pronto.")

    def home_page(self):
        content=QWidget();layout=QVBoxLayout(content)
        layout.setSpacing(14)
        layout.addWidget(label("Medição de monitores","display"))
        layout.addWidget(label("Conecte o Íris por USB para medir. Abra o histórico para consultar ensaios salvos.","muted",True))
        connection,form=card("Equipamento")
        row=QHBoxLayout()
        self.port=QComboBox();self.port.setEditable(True);row.addWidget(self.port,1)
        rescan=QPushButton("Buscar portas");rescan.clicked.connect(self.refresh_ports);row.addWidget(rescan)
        self.connect_button=QPushButton("Conectar");self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(lambda:self.guard(self.connect_device));row.addWidget(self.connect_button)
        self.disconnect_button=QPushButton("Desconectar")
        self.disconnect_button.clicked.connect(lambda:self.guard(self.disconnect_device));row.addWidget(self.disconnect_button)
        form.addLayout(row)
        self.device_info=label("Selecione a porta COM do Íris.","muted",True)
        form.addWidget(self.device_info);layout.addWidget(connection)
        self.device_detail=label("","muted",True);form.addWidget(self.device_detail)
        row=QGridLayout()
        for i,(title,body,button,screen) in enumerate((
            ("Nova medição","Identifique o monitor e configure as transições.","Configurar medição",1),
            ("Histórico","Abra, importe ou exporte uma sessão.","Abrir histórico",5),
        )):
            panel,actions=card(title,body)
            action=QPushButton(button)
            action.clicked.connect(lambda checked=False,screen=screen:self.navigate(screen))
            actions.addWidget(action);row.addWidget(panel,0,i)
        layout.addLayout(row)
        help_button=QPushButton("Guia de uso")
        help_button.clicked.connect(lambda:self.open_file("docs/INICIO_RAPIDO.md"))
        layout.addWidget(help_button,alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return scroll(content)

    def tools_page(self):
        content=QWidget();layout=QVBoxLayout(content)
        items=(
            ("Diagnóstico", "Tensão, ruído, captura sem estímulo e controle de ganho.",4),
            ("Comparações", "Compare curvas e condições de sessões salvas.",3),
            ("Campanhas", "Continue ou exporte uma sequência de ensaios.",9),
        )
        for name,description,index in items:
            panel,actions=card(name,description)
            button=QPushButton("Abrir "+name.lower())
            button.clicked.connect(lambda checked=False,index=index:self.navigate(index))
            actions.addWidget(button,alignment=Qt.AlignmentFlag.AlignLeft);layout.addWidget(panel)
        logs=QPushButton("Abrir pasta de dados e logs")
        logs.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))))
        layout.addWidget(logs,alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return scroll(content)

    def history_page(self):
        w=QWidget();v=QVBoxLayout(w);h=QHBoxLayout();self.query=QLineEdit();self.query.setPlaceholderText("Buscar monitor, Hz, overdrive, ADC, Rf, data ou identificação…")
        h.addWidget(self.query,1);self.kind=combo(["Todos","Monitores","Bancada"]);h.addWidget(self.kind)
        b=QPushButton("Atualizar");h.addWidget(b);b.clicked.connect(self.refresh_history);v.addLayout(h)
        self.query.textChanged.connect(self.refresh_history);self.kind.currentTextChanged.connect(self.refresh_history)
        self.history_table=table(["Data UTC","Ensaio","Tipo","Monitor / ADC","Estado"]);v.addWidget(self.history_table,1)
        self.history_table.cellDoubleClicked.connect(lambda *_:self.guard(self.open_history))
        row=QHBoxLayout()
        for text,method in (("Abrir sessão",self.open_history),("Importar ZIP / JSON / CSV",self.import_file),("Importar pasta antiga",self.import_folder),
                            ("Exportar sessão ZIP",self.history_export),("Relatório",self.history_report)):
            b=QPushButton(text);b.clicked.connect(lambda checked=False,m=method:self.guard(m));row.addWidget(b)
        v.addLayout(row);v.addWidget(label("Pilotos, referências e falhas permanecem no histórico. Só capturas de medição válidas entram nas médias finais. Bancada fica identificada separadamente.","muted",True))
        return w

    def settings_page(self):
        w=QWidget();v=QVBoxLayout(w)
        group,c=card("Referências visuais e dados","As cores opcionais representam metas definidas pelo operador. Não significam aprovação VESA nem nota de qualidade do monitor.")
        f=QFormLayout();display=self.store.setting("display",{})
        self.visual_targets=QCheckBox("Usar faixas de cor nas métricas");self.visual_targets.setChecked(display.get("targets",False));f.addRow(self.visual_targets)
        self.g2g_low=spin(display.get("g2g_low",3.),.01,1000,2," ms");self.g2g_high=spin(display.get("g2g_high",5.),.01,1000,2," ms")
        self.os_low=spin(display.get("os_low",5.),0,1000,2,"%");self.os_high=spin(display.get("os_high",15.),0,1000,2,"%")
        for text,widget in (("G2G · abaixo da primeira meta (verde)",self.g2g_low),("G2G · acima da segunda meta (laranja)",self.g2g_high),
                            ("Pico · abaixo da primeira meta (verde)",self.os_low),("Pico · acima da segunda meta (laranja)",self.os_high)):
            f.addRow(text,widget)
        self.ref_ms=spin(display.get("reference_ms",5.),.01,1000,2," ms");self.ref_label=QLineEdit(display.get("reference_label","Referência do projeto"))
        f.addRow("Linha vertical desde t10",self.ref_ms);f.addRow("Legenda da linha",self.ref_label)
        c.addLayout(f);c.addWidget(label("Cores: verde = abaixo da 1ª meta; amarelo = entre as metas; laranja = acima da 2ª meta. Limites escolhidos pelo usuário; desativados por padrão. 10/90% são níveis relativos, não critérios de aprovação.","muted",True))
        save=QPushButton("Salvar preferências");save.setObjectName("primary");save.clicked.connect(lambda:self.guard(self.save_preferences));c.addWidget(save);v.addWidget(group)
        group,c=card("Armazenamento e calibração","Amostras originais em arquivos locais com SHA-256; SQLite guarda índice, condições e revisões.")
        c.addWidget(label(str(self.store.root),"muted",True))
        vref_label=label("MCP3208 · tensão = código × VREF / 4096. O ADC interno mantém os códigos brutos.","muted",True);c.addWidget(vref_label)
        self.calibration=QPlainTextEdit(json.dumps(self.store.setting("gain_calibration",{}),indent=2,ensure_ascii=False));self.calibration.setMaximumHeight(100)
        calibration_label=label('Calibração de faixas (registro JSON, ex.: {"G0": {"rf_ohm": 47120, "metodo": "corrente conhecida", "data": "..."}}). Não modifica os códigos nem substitui validação de largura de banda.',"muted",True);c.addWidget(calibration_label);c.addWidget(self.calibration)
        row=QHBoxLayout();b=QPushButton("Salvar registro de calibração");b.clicked.connect(lambda:self.guard(self.save_calibration));row.addWidget(b)
        self.settings_technical=[vref_label,calibration_label,self.calibration,b]
        b=QPushButton("Abrir pasta de dados");b.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))));row.addWidget(b)
        c.addLayout(row);v.addWidget(group)
        v.addWidget(label("Para mudar a pasta de dados, inicie com --data-dir CAMINHO. Faça backup da pasta completa ou exporte as sessões ZIP; o banco isolado não contém as amostras.","muted",True));v.addStretch()
        return scroll(w)

    def guard(self,func):
        try:return func()
        except Exception as exc:
            self.notify(str(exc));self.log_exception(exc)
            QMessageBox.warning(self,"Íris · operação não concluída",str(exc))

    def log_exception(self,exc):
        with (self.store.root/"erros.log").open("a",encoding="utf8") as f:
            f.write("".join(traceback.format_exception(exc))+"\n")

    def notify(self,text):
        self.statusBar().showMessage(str(text),20000)

    def navigate(self,index):
        if index in (3,4,7,9) and not self.technical_mode.isChecked():
            self.technical_mode.setChecked(True)
        self.stack.setCurrentIndex(index);self.nav[index].setChecked(True);self.page_title.setText(self.nav[index].text())
        if index==2:self.analysis.refresh_sessions()
        elif index==3:self.compare.refresh()
        elif index==5:self.refresh_history()
        elif index==8:self.publication.refresh_sessions()

    def toggle_technical(self,value):
        self.store.set_setting("advanced_mode",value)
        if not hasattr(self,"analysis"):
            return
        for index in (3,4,7,9):self.nav[index].setVisible(value)
        self.advanced_caption.setVisible(value)
        self.device_detail.setVisible(value)
        self.measure.set_advanced(value)
        self.analysis.set_advanced(value)
        for control in self.settings_technical:control.setVisible(value)
        if not value and self.stack.currentIndex() in (3,4,7,9):
            self.navigate(0)

    def refresh_ports(self):
        current=self.port.currentData() or self.port.currentText() or self.store.setting("port","")
        self.port.clear()
        for device,description in ports():self.port.addItem(f"{device} · {description}",device)
        index=self.port.findData(current)
        if index>=0:self.port.setCurrentIndex(index)
        elif current:self.port.setEditText(current)

    def connect_device(self):
        if self.acquisition.running or self.bench.running or self.bench.snapshot_pending:raise ValueError("Encerre a aquisição antes de trocar a conexão.")
        port=self.port.currentData() if self.port.currentText()==self.port.itemText(self.port.currentIndex()) else self.port.currentText().strip()
        port=port or self.port.currentText().strip()
        if not port:raise ValueError("Selecione ou digite a porta COM do ESP32.")
        self.store.set_setting("port",port);self.connecting=True;self.connect_button.setEnabled(False)
        self.device_info.setText("Abrindo "+port+"; aguardando HELLO…");self.device.submit("connect",dict(port=port))

    def disconnect_device(self):
        if self.acquisition.running or self.bench.running or self.bench.snapshot_pending:raise ValueError("Encerre a aquisição primeiro.")
        self.device.submit("disconnect")

    def device_result(self,ident,kind,result):
        if kind=="connect":
            self.connecting=False;self.connect_button.setEnabled(True)
            self.connection.setText("● ESP32 conectado");self.connection.setStyleSheet("color:#7ae4b5;padding:8px;")
            text=f"Firmware {result.get('fw')} · protocolo {result.get('protocol')} · {result.get('board')} · {result.get('baud',115200)} baud. "
            text+="Controle CD4066 disponível." if "gain4" in result.get("features",[]) else "Ganho fixo e voltímetro disponíveis. Atualize o firmware para controle CD4066."
            self.device_info.setText("Equipamento conectado. Você já pode configurar a medição.");self.device_detail.setText(text);self.notify("Íris conectado.")
        elif kind=="disconnect":self.set_disconnected()

    def set_disconnected(self):
        self.connection.setText("● Desconectado");self.connection.setStyleSheet("color:#ffbd69;padding:8px;")
        self.connect_button.setEnabled(True)

    def device_error(self,ident,kind,error):
        self.set_disconnected();self.connecting=False;self.device_info.setText(error["message"]+" · reconecte após conferir.")
        self.notify(error["message"])

    def busy_changed(self,*_):
        if not hasattr(self,"bench"):return
        busy=self.acquisition.running or self.bench.running or self.bench.snapshot_pending or (hasattr(self,'campaign') and self.campaign.busy())
        self.connect_button.setEnabled(not busy and not self.connecting);self.disconnect_button.setEnabled(not busy)
        self.measure.start.setEnabled(not busy);self.bench.start.setEnabled(not busy);self.bench.fast_button.setEnabled(not busy)

    def acquisition_finished(self,sid,status):
        self.refresh_history();self.analysis.open_session(sid)
        if self.stack.currentIndex()==1:
            self.navigate(2)
        self.notify("Medição salva." if status=="concluida" else "Sessão salva para revisão.")

    def refresh_history(self,*_):
        if not hasattr(self,"history_table"):return
        kind={"Monitores":"monitor","Bancada":"bancada"}.get(self.kind.currentText())
        self.history_rows=self.store.sessions(self.query.text(),kind)
        fill_table(self.history_table,[[s["created"][:19].replace("T"," "),("[SIMULAÇÃO] " if s["simulation"] else "")+s["title"],s["kind"],
            f"{s['config'].get('monitor','')} · {s['config'].get('adc','')}",s["status"]] for s in self.history_rows])

    def history_id(self):
        i=self.history_table.currentRow()
        if not 0<=i<len(self.history_rows):raise ValueError("Selecione uma sessão no histórico.")
        return self.history_rows[i]["id"]

    def open_history(self):
        sid=self.history_id();s=self.store.get_session(sid)
        if s["kind"]=="bancada":self.bench.open_session(sid);self.navigate(4)
        else:self.analysis.open_session(sid);self.navigate(2)

    def check_idle(self):
        if hasattr(self,'campaign') and self.campaign.busy():raise ValueError('Aguarde a exportação ou publicação da campanha terminar.')
        if self.acquisition.running or self.bench.running or self.bench.snapshot_pending:raise ValueError("Encerre a aquisição antes de importar ou exportar uma sessão completa.")

    def import_path(self,path):
        self.check_idle()
        if Path(path).suffix.lower()==".csv":result=import_bench_csv(self.store,path)
        else:
            from ..importers import import_recording
            result=import_recording(self.store,path)
        self.refresh_history();self.analysis.refresh_sessions();self.compare.refresh()
        self.notify("Importação concluída: "+str(result));return result

    def import_file(self):
        self.check_idle();path,_=QFileDialog.getOpenFileName(self,"Importar ensaio ou bancada","","Íris (*.zip *.json *.csv)")
        if path:self.import_path(path)

    def import_folder(self):
        self.check_idle();path=QFileDialog.getExistingDirectory(self,"Pasta dos ensaios originais")
        if path:self.import_path(path)

    def history_export(self):
        self.check_idle();sid=self.history_id()
        path,_=QFileDialog.getSaveFileName(self,"Exportar sessão completa","sessao_iris.zip","ZIP (*.zip)")
        if path:export_native(self.store,sid,path);self.notify("Sessão exportada.")

    def history_report(self):
        self.check_idle();sid=self.history_id();folder=QFileDialog.getExistingDirectory(self,"Pasta do relatório")
        if folder:
            p=report_html(self.store,sid,folder);report_pdf(p,Path(folder)/"relatorio.pdf");self.notify("Relatório salvo: "+folder)

    def save_preferences(self):
        if self.g2g_low.value()>=self.g2g_high.value() or self.os_low.value()>=self.os_high.value():raise ValueError("A primeira meta deve ser menor que a segunda.")
        value=dict(targets=self.visual_targets.isChecked(),g2g_low=self.g2g_low.value(),g2g_high=self.g2g_high.value(),os_low=self.os_low.value(),os_high=self.os_high.value(),
                   reference_ms=self.ref_ms.value(),reference_label=self.ref_label.text())
        self.store.set_setting("display",value);self.analysis.plot_current();self.notify("Preferências salvas. Cores representam metas do operador.")

    def save_calibration(self):
        value=json.loads(self.calibration.toPlainText())
        if not isinstance(value,dict):raise ValueError("Calibração deve ser um objeto JSON.")
        self.store.set_setting("gain_calibration",value);self.notify("Registro salvo; será incluído nas próximas sessões.")

    def metric_color(self,value,key):
        display=self.store.setting("display",{})
        if value is None or not display.get("targets"):return COLORS[0] if key=="g2g" else COLORS[1]
        if value<=display.get(key+"_low",3 if key=="g2g" else 5):return "#7ae4b5"
        if value<=display.get(key+"_high",5 if key=="g2g" else 15):return "#ffd166"
        return "#ff9a73"

    def open_file(self,path):
        file=self.base/path
        if file.exists():
            if file.suffix==".md":
                from .help_viewer import HelpViewer
                dialog=HelpViewer(file,self);dialog.show()
            else:QDesktopServices.openUrl(QUrl.fromLocalFile(str(file)))
        else:self.notify("Arquivo não encontrado: "+str(file))

    def closeEvent(self,event):
        if self.campaign.busy():
            event.ignore();self.notify('Aguarde a exportação ou publicação da campanha terminar.');return
        if self.publication.busy():
            event.ignore();self.notify("Aguarde a geração ou o envio do relatório terminar antes de fechar.");return
        if self.acquisition.running:self.acquisition.cancel()
        if self.bench.running:self.bench.end()
        if self.acquisition.running or self.bench.running or self.bench.snapshot_pending:
            event.ignore();QTimer.singleShot(300,self.close);return
        if not self._closing:
            self._closing=True;self.device.shutdown()
        if self.device.worker.isRunning():
            event.ignore();QTimer.singleShot(100,self.close);return
        event.accept()
