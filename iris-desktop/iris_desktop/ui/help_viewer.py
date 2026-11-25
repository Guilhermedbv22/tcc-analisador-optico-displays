from pathlib import Path
from PySide6.QtCore import Qt,QUrl,QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QTextBrowser,QPushButton,QScrollArea


class HelpViewer(QDialog):
    """Guias offline integrados; não dependem de associação de arquivos Markdown."""
    def __init__(self,path,parent=None):
        super().__init__(parent);self.setWindowTitle("Íris · guia de bancada")
        self.resize(980,760);self.path=Path(path).resolve()
        v=QVBoxLayout(self);row=QHBoxLayout()
        for title,filename in (("Início","INICIO_RAPIDO.md"),("Circuito A","CIRCUITO_A.md"),("Circuito B","CIRCUITO_B.md"),("Método","METODO.md")):
            b=QPushButton(title);b.clicked.connect(lambda checked=False,f=filename:self.load(self.path.parent/f));row.addWidget(b)
        v.addLayout(row)
        self.browser=QTextBrowser();self.browser.setOpenLinks(False);self.browser.anchorClicked.connect(self.open_link);v.addWidget(self.browser)
        self.load(self.path)

    def load(self,path):
        path=Path(path).resolve()
        if not path.exists():return
        self.path=path;self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent)+"/"))
        self.browser.setMarkdown(path.read_text(encoding="utf8"));self.browser.moveCursor(self.browser.textCursor().MoveOperation.Start)

    def open_link(self,url):
        target=self.browser.document().baseUrl().resolved(url)
        if target.isLocalFile():
            path=Path(target.toLocalFile())
            if path.suffix.lower()==".md":self.load(path)
            elif path.suffix.lower()==".svg":
                dialog=QDialog(self);dialog.setWindowTitle(path.name);dialog.resize(1100,800)
                v=QVBoxLayout(dialog);area=QScrollArea();svg=QSvgWidget(str(path));svg.setFixedSize(svg.sizeHint().boundedTo(QSize(1440,1100)))
                area.setWidget(svg);v.addWidget(area);dialog.show()
            else:QDesktopServices.openUrl(target)
        else:QDesktopServices.openUrl(target)
