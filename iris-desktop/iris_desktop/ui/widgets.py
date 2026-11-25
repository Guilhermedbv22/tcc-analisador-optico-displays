from pathlib import Path
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QFrame,QFormLayout,
    QSpinBox,QDoubleSpinBox,QLineEdit,QComboBox,QCheckBox,QScrollArea,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QHeaderView,QGridLayout,QSizePolicy)
from ..analysis import curve

COLORS = ["#68bdff","#eeaaff","#4ee2cd","#ffd166","#ff9a73","#c1b0ff","#8de3a4","#f796bd"]
STYLE = '''
QWidget { background:#0a0e16; color:#e1e9f5; font-family:"Segoe UI"; font-size:10pt; }
QMainWindow { background:#0a0e16; }
QFrame#sidebar { background:#101722; border-right:1px solid #293646; }
QFrame#card { background:#131c29; border:1px solid #293646; border-radius:10px; }
QLabel { background:transparent; }
QLabel#muted { color:#9eb1cc; }
QLabel#title {font-size:21pt; font-weight:650;}
QLabel#heading {font-size:15pt; font-weight:600;}
QPushButton { background:#182335; border:1px solid #314155; padding:8px 13px; border-radius:6px; }
QPushButton:hover { background:#21324a; }
QPushButton:checked { background:#19324b; border:1px solid #64d0ff; }
QPushButton#primary { background:#64d0ff; color:#07121f; border:1px solid #64d0ff; font-weight:600; }
QPushButton#navigation {text-align:left;background:transparent;border:1px solid transparent;padding:8px 10px;}
QPushButton#navigation:hover {background:#182335;}
QPushButton#navigation:checked {background:#19324b;border-color:#36516d;color:#dff5ff;}
QPushButton:focus,QLineEdit:focus,QComboBox:focus {border-color:#64d0ff;}
QLabel#display {font-size:28pt;font-weight:600;}
QPushButton:disabled { color:#6d8099; background:#182638; border-color:#293646; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QTextEdit { background:#111a27; border:1px solid #35465b; border-radius:4px; padding:5px; selection-background-color:#19659a; }
QComboBox QAbstractItemView { background:#15253d; selection-background-color:#225788; }
QTabWidget::pane { border:1px solid #293646; border-radius:6px; }
QTabBar::tab { background:#131c29; padding:9px 15px; border-bottom:2px solid transparent; }
QTabBar::tab:selected {color:#7ecaff; border-bottom:2px solid #4caff8; background:#1b2e48;}
QTableWidget,QListWidget,QTreeWidget { background:#111a27; alternate-background-color:#151e2d; border:1px solid #293646; gridline-color:#283545; selection-background-color:#194d7b; }
QHeaderView::section { background:#1a2536; color:#cbd9ec; padding:7px; border:none; border-right:1px solid #2d4663; }
QScrollArea { border:none; }
QScrollBar:vertical {width:10px;background:#111a27;} QScrollBar::handle:vertical {background:#35506e;min-height:30px;border-radius:4px;}
QScrollBar:horizontal {height:10px;background:#111a27;} QScrollBar::handle:horizontal {background:#35506e;min-width:30px;border-radius:4px;}
QGroupBox {border:1px solid #293646;border-radius:6px;margin-top:12px;padding:12px;} QGroupBox::title {subcontrol-origin:margin;left:10px;}
QProgressBar {background:#172740;border:1px solid #2c4867;border-radius:4px;text-align:center;} QProgressBar::chunk {background:#64d0ff;}
QSplitter::handle {background:#263c56;}
QToolTip {background:#223953;color:#f1f6ff;border:1px solid #5ba9dc;padding:8px;}
QStatusBar {color:#9eb1cc;background:#111a27;}
'''


def label(text, name=None, wrap=False):
    w=QLabel(text)
    if name:w.setObjectName(name)
    w.setWordWrap(wrap)
    w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return w


def card(title, body=""):
    w=QFrame();w.setObjectName("card");v=QVBoxLayout(w);v.setContentsMargins(18,16,18,16)
    v.addWidget(label(title,"heading",True))
    if body:v.addWidget(label(body,"muted",True))
    return w,v


def scroll(widget):
    area=QScrollArea();area.setWidgetResizable(True);area.setWidget(widget)
    return area


def spin(value,lo,hi,decimals=0,suffix=""):
    w=QDoubleSpinBox() if decimals else QSpinBox()
    if decimals:w.setDecimals(decimals)
    w.setRange(lo,hi);w.setValue(value);w.setSuffix(suffix)
    w.setKeyboardTracking(False)
    return w


def combo(values,current=None):
    w=QComboBox();w.addItems([str(v) for v in values])
    if current is not None:w.setCurrentText(str(current))
    return w


def table(headers):
    w=QTableWidget(0,len(headers));w.setHorizontalHeaderLabels(headers)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setAlternatingRowColors(True);w.verticalHeader().hide()
    w.horizontalHeader().setStretchLastSection(True)
    return w


def fill_table(widget,rows,tooltips=None):
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            cell=QTableWidgetItem("—" if value is None else str(value))
            if tooltips and i<len(tooltips):cell.setToolTip(str(tooltips[i]))
            widget.setItem(i,j,cell)
    widget.resizeColumnsToContents()


def fmt(x,decimals=3,suffix=""):
    return "N/D" if x is None else f"{x:.{decimals}f}{suffix}"


class Metric(QFrame):
    def __init__(self,title,color="#68bdff"):
        super().__init__();self.setObjectName("card")
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,12)
        self.title=label(title,"muted",True);layout.addWidget(self.title)
        self.value=label("—");self.value.setStyleSheet(f"font-size:19pt;font-weight:600;color:{color}")
        layout.addWidget(self.value)
        self.detail=label("","muted",True);layout.addWidget(self.detail)
        self.setMinimumHeight(88)

    def set(self,value,detail="",color=None):
        self.value.setText(value);self.detail.setText(detail)
        if color:self.value.setStyleSheet(f"font-size:19pt;font-weight:600;color:{color}")


def plot_widget(y="Código ADC",x="Tempo",units="ms"):
    plot=pg.PlotWidget(background="#101722")
    plot.showGrid(x=True,y=True,alpha=.15)
    plot.setLabel("bottom",x,units=units);plot.setLabel("left",y)
    plot.getPlotItem().setContentsMargins(10,10,16,10)
    plot.setMinimumHeight(200)
    plot.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
    return plot


class CurveView(QWidget):
    def __init__(self):
        super().__init__()
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.plot=plot_widget();layout.addWidget(self.plot,1)
        self.plot.setMinimumHeight(260)
        self.setMinimumHeight(385)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.legend=QGridLayout();layout.addLayout(self.legend)
        self.cursor_label=label("Aponte na curva para ver tempo e valor.","muted",True)
        layout.addWidget(self.cursor_label)
        self.data=None
        self.proxy=pg.SignalProxy(self.plot.scene().sigMouseMoved,rateLimit=30,slot=self._mouse)
        self.vline=pg.InfiniteLine(angle=90,pen=pg.mkPen("#627b99",style=Qt.PenStyle.DotLine))

    def reset_legend(self, entries):
        while self.legend.count():
            item=self.legend.takeAt(0)
            if item.widget():item.widget().deleteLater()
        for i,(name,color) in enumerate(entries):
            w=label("━  "+name,wrap=True);w.setStyleSheet(f"color:{color};font-size:9pt")
            self.legend.addWidget(w,i//3,i%3)

    def show_curve(self,cap,result,unit="%",vref=3.3,options=None):
        opt=dict(raw=True,filtered=True,plateaus=True,thresholds=True,settling=True,
                 references=False,reference_ms=5.,reference_label="Referência do projeto",align=False)
        opt.update(options or {})
        self.plot.clear(); entries=[]
        try:t,y,f=curve(cap,result,unit=unit,vref=vref,align=opt["align"])
        except ValueError:unit="ADC";t,y,f=curve(cap,result,unit=unit,vref=vref,align=opt["align"])
        self.data=(t,y,f,unit)
        if opt["raw"]:
            self.plot.plot(t,y,pen=pg.mkPen(COLORS[0],width=1),connect="finite");entries.append(("Bruto",COLORS[0]))
        if opt["filtered"]:
            self.plot.plot(t,f,pen=pg.mkPen(COLORS[1],width=2),connect="finite");entries.append((f"Mediana {result.get('criterios',{}).get('mediana_amostras',3)}",COLORS[1]))
        self.plot.setLabel("left", "Resposta relativa (%)" if unit=="%" else "Tensão no ADC (V)" if unit=="V" else "Código ADC")
        self.plot.setLabel("bottom","Tempo desde t10" if opt["align"] else "Tempo desde a primeira amostra",units="ms")
        a,b=result.get("inicial_adc"),result.get("final_adc")
        shift=result.get("t10_ms",0) or 0 if opt["align"] else 0
        if a is not None and b is not None:
            start,end=(0,100) if unit=="%" else (a*vref/4096,b*vref/4096) if unit=="V" else (a,b)
            if opt["plateaus"]:
                for v,name,color in ((start,"Partida",COLORS[2]),(end,"Alvo",COLORS[3])):
                    self.plot.addItem(pg.InfiniteLine(v,angle=0,pen=pg.mkPen(color,style=Qt.PenStyle.DashLine)));entries.append((name,color))
            if opt["thresholds"]:
                for p,name,color in ((.1,"10%", "#80d8ff"),(.9,"90%","#c1b0ff")):
                    self.plot.addItem(pg.InfiniteLine(start+p*(end-start),angle=0,pen=pg.mkPen(color,style=Qt.PenStyle.DotLine)));entries.append((name,color))
            if result.get("t10_ms") is not None:
                t10,t90=result["t10_ms"]-shift,result["t90_ms"]-shift
                region=pg.LinearRegionItem((t10,t90),movable=False,brush=pg.mkBrush(90,180,255,28),pen=pg.mkPen(None));region.setZValue(-8);self.plot.addItem(region)
                entries.append(("Intervalo G2G 10–90%",COLORS[0]))
                if opt["settling"]:
                    tol=result["criterios"]["tolerancia_acomodacao"]*abs(end-start)
                    band=pg.LinearRegionItem((end-tol,end+tol),orientation="horizontal",movable=False,brush=pg.mkBrush(78,226,160,20),pen=pg.mkPen(None));band.setZValue(-9);self.plot.addItem(band)
                    entries.append((f"Acomodação ±{result['criterios']['tolerancia_acomodacao']*100:g}%",COLORS[6]))
                    if result.get("acomodacao_ms") is not None:
                        self.plot.addItem(pg.InfiniteLine(t10+result["acomodacao_ms"],angle=90,pen=pg.mkPen(COLORS[6],style=Qt.PenStyle.DashLine)))
                if opt["references"]:
                    self.plot.addItem(pg.InfiniteLine(t10+opt["reference_ms"],angle=90,pen=pg.mkPen(COLORS[4],style=Qt.PenStyle.DashDotLine)))
                    entries.append((f"{opt['reference_label']} · {opt['reference_ms']:g} ms",COLORS[4]))
                lo=np.searchsorted(t,t10);hi=np.searchsorted(t,t[-1]-result["criterios"]["patamar_final_ms"])
                if hi>lo:
                    pk=lo+int(np.argmax(f[lo:hi]) if end>start else np.argmin(f[lo:hi]))
                    self.plot.plot([t[pk]],[f[pk]],pen=None,symbol="o",symbolSize=8,symbolBrush=COLORS[4]);entries.append((result.get("peak_name","Pico"),COLORS[4]))
        self.plot.addItem(self.vline,ignoreBounds=True)
        self.reset_legend(entries)
        self.plot.enableAutoRange()

    def _mouse(self,event):
        if self.data is None:return
        point=event[0]
        if not self.plot.sceneBoundingRect().contains(point):return
        p=self.plot.plotItem.vb.mapSceneToView(point)
        t,y,f,unit=self.data
        i=int(np.clip(np.searchsorted(t,p.x()),0,len(t)-1))
        self.vline.setPos(t[i])
        self.cursor_label.setText(f"t = {t[i]:.3f} ms   ·   bruto = {y[i]:.4f} {unit}   ·   processado = {f[i]:.4f} {unit}   ·   amostra {i}")
