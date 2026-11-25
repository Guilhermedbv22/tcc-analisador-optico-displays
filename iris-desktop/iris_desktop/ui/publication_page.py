from pathlib import Path
from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPlainTextEdit, QPushButton, QCheckBox, QFileDialog, QApplication)
from .widgets import label, scroll, spin
from ..publication import DEFAULT_SITE, campaign_packages, publish_package


class UploadThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, paths, site, parent=None):
        super().__init__(parent)
        self.paths, self.site = paths, site

    def run(self):
        try:
            receipts=[]
            for path in self.paths:
                receipts.append(publish_package(path,self.site))
            self.completed.emit(receipts)
        except Exception as exc:
            self.failed.emit(str(exc))


class PublicationPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app, self.worker, self.generated = app, None, None
        self.url = ""
        self.generating = False
        outer = QVBoxLayout(self)
        content = QWidget(); layout = QVBoxLayout(content)
        layout.addWidget(label("Publicar ensaio", "heading"))
        form = QFormLayout()
        self.sessions = QComboBox(); form.addRow("Sessão de monitor", self.sessions)
        self.sessions.currentIndexChanged.connect(self.session_changed)
        self.model = QLineEdit(); form.addRow("Modelo exato", self.model)
        self.overdrive = QLineEdit(); form.addRow("Modo de overdrive", self.overdrive)
        self.hz = spin(180, 1, 2000, 2); form.addRow("Frequência (Hz)", self.hz)
        self.operator = QLineEdit(); self.operator.setPlaceholderText("Opcional · nome público ou equipe")
        form.addRow("Autor público", self.operator)
        self.conclusion = QPlainTextEdit(); self.conclusion.setMaximumHeight(120)
        self.conclusion.setPlaceholderText("O que foi observado nesta configuração? Não inclua dados pessoais.")
        form.addRow("Conclusão", self.conclusion)
        self.site = QLineEdit(app.store.setting("publication_site", DEFAULT_SITE)); form.addRow("Site", self.site)
        layout.addLayout(form)
        self.session_info = label("Selecione uma sessão concluída.", "muted", True); layout.addWidget(self.session_info)

        self.consent = QCheckBox("Revisei a identificação e quero disponibilizar este relatório publicamente.")
        layout.addWidget(self.consent)
        actions = QHBoxLayout()
        self.save = QPushButton("Exportar pacote")
        self.send = QPushButton("Publicar no site"); self.send.setObjectName("primary")
        self.open = QPushButton("Abrir relatório no site"); self.open.setEnabled(False)
        actions.addWidget(self.save); actions.addWidget(self.send); actions.addWidget(self.open)
        layout.addLayout(actions)
        self.save.clicked.connect(lambda: app.guard(self.save_package))
        self.send.clicked.connect(lambda: app.guard(self.send_package))
        self.open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        self.status = label("O relatório pode ser gerado sem internet e enviado depois.", "muted", True)
        self.status.setTextInteractionFlags(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status); layout.addStretch()
        outer.addWidget(scroll(content))

    def refresh_sessions(self, sid=None):
        selected = sid or self.sessions.currentData()
        self.sessions.blockSignals(True); self.sessions.clear()
        self.sessions.addItem("Selecione…", None)
        for s in self.app.store.sessions(kind="monitor"):
            if s["status"] != "em_andamento":
                self.sessions.addItem(("[SIMULAÇÃO] " if s["simulation"] else "")+s["title"]+" · "+s["created"][:16], s["id"])
        i = self.sessions.findData(selected)
        self.sessions.setCurrentIndex(max(i, 0)); self.sessions.blockSignals(False)
        self.session_changed()

    def open_session(self, sid):
        self.refresh_sessions(sid)

    def session_changed(self, *_):
        sid = self.sessions.currentData()
        self.generated = None; self.url = ""; self.open.setEnabled(False); self.consent.setChecked(False)
        if not sid:
            return
        s = self.app.store.get_session(sid); c = s["config"]
        self.model.setText(c.get("monitor") or ""); self.overdrive.setText(c.get("overdrive") or "")
        self.hz.setValue(c.get("refresh_hz") or 180)
        self.conclusion.clear()
        rows = [r for r in self.app.store.rows(sid) if r["phase"] == "medicao"]
        self.session_info.setText(("SIMULAÇÃO · " if s["simulation"] else "Medição física · ")+f"{len(rows)} capturas · {sum(bool(r.get('valida')) for r in rows)} válidas · {c.get('adc', 'ADC não informado')}")

    def metadata(self):
        return dict(model=self.model.text(), overdrive=self.overdrive.text(), refresh_hz=self.hz.value(),
                    operator=self.operator.text(), conclusion=self.conclusion.toPlainText())

    def busy(self):
        return self.generating or (self.worker is not None and self.worker.isRunning())

    def set_busy(self, busy):
        for w in (self.save, self.send, self.sessions, self.model, self.overdrive, self.hz,
                  self.operator, self.conclusion, self.site, self.consent):
            w.setEnabled(not busy)

    def generate(self, folder):
        self.app.check_idle()
        sid = self.sessions.currentData()
        if not sid:
            raise ValueError("Selecione uma sessão concluída.")
        self.generating = True; self.set_busy(True)
        self.status.setText("Gerando PDF, gráficos e pacote público…")
        QApplication.processEvents()
        try:
            self.generated = campaign_packages(self.app.store,sid,folder,self.metadata(),documents=True)
            if not self.generated:raise ValueError("A sessão não contém transições.")

            return self.generated
        finally:
            self.generating = False; self.set_busy(False)

    def save_package(self):
        if not self.sessions.currentData():
            raise ValueError("Selecione uma sessão concluída.")
        folder = QFileDialog.getExistingDirectory(self, "Salvar relatório público")
        if folder:
            paths = self.generate(folder)
            self.status.setText(f"{len(paths)} pacote(s) em {folder}.")

    def send_package(self):
        if not self.consent.isChecked():
            raise ValueError("Revise os campos e marque a opção de publicação pública.")
        sid = self.sessions.currentData()
        if not sid:
            raise ValueError("Selecione uma sessão concluída.")
        if self.app.store.get_session(sid)["simulation"]:
            raise ValueError("Selecione uma medição realizada com o Íris.")
        paths = self.generate(self.app.store.root/"public_reports"/sid)
        self.app.store.set_setting("publication_site", self.site.text().strip())
        self.set_busy(True); self.status.setText("Enviando relatório ao site…")
        self.worker = UploadThread(paths, self.site.text(), self)
        self.worker.completed.connect(self.uploaded); self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.set_busy(False))
        self.worker.start()

    def uploaded(self, receipts):
        self.url = receipts[0]["url"] + ("&completo=1" if len(receipts)>1 else "")
        self.open.setEnabled(True)
        self.status.setText("Relatório disponível: "+self.url)
        for receipt in receipts:
            self.app.store.event(self.sessions.currentData(),"publicacao_site",{"id":receipt["id"],"url":receipt["url"]})
        self.app.notify("Relatório publicado.")

    def failed(self, message):
        self.status.setText(message+"\nOs pacotes foram salvos. É possível repetir o envio.")
