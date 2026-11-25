"""Diagramas SVG determinísticos. Redes com nomes iguais estão conectadas."""
from pathlib import Path
from html import escape
import csv

OUT=Path(__file__).resolve().parents[1]/"docs/esquemas"
BLUE="#176d9d";INK="#19344d";WIRE="#258073";FB="#9347a4"

class Drawing:
    def __init__(self,title,subtitle,w=1440,h=1000):
        self.w,self.h=w,h
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',f'<rect width="{w}" height="{h}" fill="#fff"/>']
        self.text(40,48,title,28,BLUE,True);self.text(40,82,subtitle,16)
        self.line(40,105,w-40,105,"#c4d4e2",2)
    def text(self,x,y,text,size=16,color=INK,bold=False,anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="DejaVu Sans,Segoe UI,sans-serif" font-size="{size}" fill="{color}" font-weight="{"bold" if bold else "normal"}" text-anchor="{anchor}">{escape(str(text))}</text>')
    def line(self,x,y,a,b,color=WIRE,width=3):
        self.parts.append(f'<line x1="{x}" y1="{y}" x2="{a}" y2="{b}" stroke="{color}" stroke-width="{width}"/>')
    def path(self,points,color=WIRE,width=3):
        self.parts.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"/>')
    def dot(self,x,y,color=WIRE):self.parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
    def box(self,x,y,w,h,color=INK):self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="white" stroke="{color}" stroke-width="2"/>')
    def ground(self,x,y):
        self.line(x,y,x,y+12)
        for dy,dx in ((12,18),(20,12),(28,6)):self.line(x-dx,y+dy,x+dx,y+dy)
    def resistor(self,x,y,name,value,color=INK):
        self.line(x-60,y,x-38,y,color);self.box(x-38,y-9,76,18,color);self.line(x+38,y,x+60,y,color)
        self.text(x,y-23,name+" · "+value,15,color,anchor="middle")
    def cap(self,x,y,name,value,color=INK):
        self.line(x-60,y,x-8,y,color);self.line(x-8,y-15,x-8,y+15,color)
        self.line(x+8,y-15,x+8,y+15,color);self.line(x+8,y,x+60,y,color)
        self.text(x,y-24,name+" · "+value,15,color,anchor="middle")
    def opamp(self,x,y,channel="A",pminus=2,pplus=3,pout=1):
        self.path([(x,y-65),(x,y+65),(x+130,y),(x,y-65)],INK,3)
        self.text(x+14,y-22,"−",24);self.text(x+14,y+41,"+",24)
        self.text(x-8,y-41,str(pminus),15,anchor="end");self.text(x-8,y+34,str(pplus),15,anchor="end")
        self.text(x+136,y-8,str(pout),15);self.text(x+130,y+92,"U1"+channel+" · MCP6022",17,BLUE,True,anchor="middle")
    def save(self,name):
        self.parts.append('</svg>');(OUT/name).write_text(''.join(self.parts),encoding="utf8")

def adc():
    d=Drawing("ÍRIS · ligação comum do ADC e ESP32","MCP3208 DIP16, SPI modo 0, VDD=VREF=3V3. Pontos com a mesma rede estão ligados.")
    d.box(480,170,330,440);d.text(645,200,"U2 · MCP3208",23,BLUE,True,anchor="middle")
    for i in range(8):
        y=245+i*45;d.line(410,y,480,y);d.text(495,y+5,f"{i+1} · CH{i}")
        d.text(395,y+5,"SINAL" if i==0 else "TESTE / GND se sem uso",14,anchor="end")
    rows=[(16,"VDD","3V3"),(15,"VREF","3V3"),(14,"AGND","GND"),(13,"CLK","GPIO18"),
          (12,"DOUT","GPIO19"),(11,"DIN","GPIO23"),(10,"CS","GPIO27"),(9,"DGND","GND")]
    for i,(pin,name,net) in enumerate(rows):
        y=245+i*45;d.text(795,y+5,f"{pin} · {name}",16,anchor="end");d.line(810,y,960,y);d.text(975,y+5,net,17,BLUE,True)
    d.text(40,700,"Desacoplamento e referência",21,BLUE,True)
    notes=["C_ADC 100 nF: U2.16 ↔ U2.14; C_REF 100 nF: U2.15 ↔ U2.14.",
           "4,7 µF: 3V3 ↔ GND perto do ADC. CS: 10 kΩ para 3V3.",
           "ESP32: 3V3 → rail 3V3; GND → GND. Alimentação USB. SPI 18/19/23/27.",
           "Opcionais 47 Ω em série no SPI, junto ao transmissor. ADC interno: SINAL → GPIO34.",
           "VREF configurada no software é informada, não medida; não calibra a tensão do próprio rail.",
           "SINAL vem da saída do operacional por 100 Ω. Nunca 5 V diretos, nem tensão negativa."]
    for i,n in enumerate(notes):d.text(40,738+35*i,n,17)
    d.save("ADC_ESP32.svg")

def follower():
    d=Drawing("CIRCUITO A0 · teste dos seguidores","Sem fotodiodos, Rf ou Cf. Validar as soldas e ambos os canais antes de montar o TIA.")
    for index,y in enumerate((370,650)):
        x=610;minus,plus,out=(2,3,1) if index==0 else (6,5,7)
        d.opamp(x,y,"A" if index==0 else "B",minus,plus,out)
        d.line(430,y+30,x,y+30);d.text(420,y+35,"TESTE",17,BLUE,True,anchor="end")
        d.line(x+130,y,840,y);d.path([(790,y),(790,y-125),(550,y-125),(550,y-30),(x,y-30)])
        d.dot(790,y);d.resistor(930,y,"Riso","100 Ω");d.line(840,y,870,y);d.line(990,y,1120,y)
        d.text(1140,y+5,f"CH{index+1} · saída {'A' if index==0 else 'B'}",17,BLUE,True)
    d.text(40,160,"Fonte TESTE",21,BLUE,True)
    d.text(40,200,"3V3 → 10k → P75 → 10k → P50 → 10k → P25 → 10k → GND",18)
    d.text(40,237,"Escolha um ponto para TESTE; CH0 ← TESTE por 100 Ω. Canais são sequenciais.",17)
    notes=["U1.8=3V3; U1.4=GND; 100 nF entre 8–4 junto do adaptador; 2,2–4,7 µF no rail.",
           "25/50/75% do rail: saídas devem acompanhar a entrada; não exigir saída idêntica a VDD.",
           "Antes do teste CH0–GND: desligue a ponta de qualquer saída ativa, evitando curto no operacional.",
           "Para converter em TIA, retirar pontes diretas de A e ligação TESTE→3/5; seguir esquema A1."]
    for i,n in enumerate(notes):d.text(40,790+38*i,n,17)
    d.save("A0_seguidor.svg")

def tia():
    d=Drawing("CIRCUITO A1 · TIA com ganho fixo","Referência para comparar MCP6022 e MCP6002: Rf=235 kΩ, Cf inicial=8,2 pF. Alimentação 3V3.")
    d.opamp(620,490)
    d.path([(290,460),(620,460)]);d.text(300,445,"SUM",18,FB,True)
    d.line(750,490,920,490);d.dot(850,490);d.text(825,528,"OUT / TP_TIA",16,BLUE,True)
    d.resistor(990,490,"Riso","100 Ω");d.line(920,490,930,490);d.line(1050,490,1190,490)
    d.text(1200,496,"CH0",20,BLUE,True)
    d.path([(850,490),(850,220),(400,220),(400,460)],FB);d.dot(400,460,FB)
    # Apaga trecho dos três componentes para inserir símbolos em paralelo.
    d.parts.append('<rect x="465" y="200" width="330" height="43" fill="white"/>')
    d.line(400,220,555,220,FB);d.resistor(615,220,"Rf1","470 kΩ",FB);d.line(675,220,850,220,FB)
    d.path([(400,310),(555,310)],FB);d.resistor(615,310,"Rf2","470 kΩ",FB);d.line(675,310,850,310,FB)
    d.line(400,400,555,400,FB);d.cap(615,400,"Cf","8,2 pF C0G",FB);d.line(675,400,850,400,FB)
    d.line(520,520,620,520);d.ground(520,520)
    for x in (180,290):
        d.line(x,460,x,600);d.line(x-22,600,x+22,600,INK)
        d.path([(x-22,640),(x+22,640),(x,600),(x-22,640)],INK)
        d.line(x,640,x,685);d.ground(x,685)
        d.text(x,575,"K",14,FB,anchor="middle");d.text(x+20,665,"A",14)
        for yy in (605,625):d.path([(x-65,yy-12),(x-36,yy+7),(x-41,yy-6)],BLUE,2)
    d.line(180,460,290,460);d.text(80,745,"D1 // D2 · BPW34",20,BLUE,True)
    d.text(80,776,"Ânodos GND · cátodos SUM",16)
    d.text(900,640,"U1B sem uso óptico",21,BLUE,True)
    for i,n in enumerate(["3V3 → 100k → MID → 100k → GND", "MID → 100 nF → GND; U1.5 → MID", "U1.6 ↔ U1.7; saída B sem carga"]):d.text(900,679+32*i,n,16)
    notes=["U1.8=3V3; U1.4=GND; 100 nF entre 8–4 e 2,2–4,7 µF perto do adaptador.",
           "Rf/Cf antes dos 100 Ω; cabos mínimos em SUM. Compensação e banda precisam de qualificação.",
           "MCP3208 e ESP32: ver ADC_ESP32.svg. Não tocar SUM com ADC ou ponta comum durante medição."]
    for i,n in enumerate(notes):d.text(40,862+35*i,n,17)
    d.save("A1_TIA_fixo.svg")

def ranges():
    d=Drawing("CIRCUITO B · realimentação com CD4066BE","Manter o TIA, fotodiodos e ADC do A1; substituir somente a rede Rf/Cf. Valores iniciais a validar.",1500,1100)
    left,right=180,1300;d.line(left,180,left,800,FB);d.line(right,180,right,800,FB)
    d.text(left,150,"SUM = U1.2",19,FB,True,anchor="middle");d.text(right,150,"OUT = U1.1",19,BLUE,True,anchor="middle")
    for y,kind,name,val in ((220,"r","Rbase","470 kΩ"),(300,"c","Cbase","4,7 pF")):
        d.line(left,y,600,y,FB)
        (d.resistor if kind=="r" else d.cap)(660,y,name,val,FB)
        d.line(720,y,right,y,FB);d.dot(left,y,FB);d.dot(right,y,FB)
    for index,(y,res,cap,pin1,pin2,ctrl,gpio) in enumerate(((430,"52,3 kΩ","3,3 pF",2,1,13,32),(580,"127 kΩ","1,0 pF",3,4,5,33),(730,"412 kΩ","1,0 pF",9,8,6,26))):
        d.line(left,y,460,y,FB);d.resistor(520,y,f"R{index}",res,FB);d.line(580,y,850,y,FB)
        d.path([(400,y),(400,y+55),(460,y+55)],FB);d.cap(520,y+55,f"C{index}",cap,FB);d.path([(580,y+55),(700,y+55),(700,y)],FB)
        d.dot(400,y,FB);d.dot(700,y,FB)
        d.line(850,y,910,y,FB);d.dot(910,y,FB);d.line(918,y-5,1000,y-28,FB);d.dot(1015,y,FB);d.line(1015,y,right,y,FB)
        d.text(902,y-18,str(pin1),14,anchor="end");d.text(1030,y-17,str(pin2),14)
        d.text(975,y+43,f"CD chave {index+1}",17,BLUE,True,anchor="middle")
        d.text(970,y-70,f"GPIO{gpio} → 330 Ω → controle {ctrl}",15,BLUE,anchor="middle")
        d.text(970,y-47,f"controle {ctrl} → 100 kΩ → GND",15,anchor="middle")
        d.dot(left,y,FB);d.dot(right,y,FB)
    d.text(40,880,"CD4066BE: pino 14 = 3V3; pino 7 = GND; 100 nF entre 14–7; 2,2 µF no rail.",18,BLUE,True)
    notes=["Sem uso: pinos 10, 11 e 12 no GND. Não há SN74HCT125N nesta versão.",
           "G0: somente controle 13 HIGH; G1: somente 5 HIGH; G2: somente 6 HIGH; G3: todos LOW.",
           "Ganho ideal: 47,063 / 99,983 / 219,546 / 470 kΩ. RON e parasitas alteram ganho e banda.",
           "Chaves no lado OUT; ramo permanente nunca abre. Reset deixa G3; habilitar seleciona G0.",
           "Cf são pontos iniciais, não valores de estabilidade garantida; qualificar todas as faixas antes de automático."]
    for i,n in enumerate(notes):d.text(40,920+31*i,n,17)
    d.save("B_TIA_autoranging.svg")

def connections():
    rows=[]
    def add(part,pin,net,comment=""):rows.append(dict(componente=part,pino=pin,rede=net,observacao=comment))
    for pin,net in ((1,"OUT"),(2,"SUM"),(3,"GND"),(4,"GND"),(5,"MID"),(6,"OUT_B"),(7,"OUT_B"),(8,"3V3")):add("U1 MCP6022",pin,net)
    for pin in range(1,9):add("U2 MCP3208",pin,"ADC_CH0" if pin==1 else f"CH{pin-1}","GND se sem uso; desconectar para teste de bancada")
    for pin,net in ((9,"GND"),(10,"GPIO27"),(11,"GPIO23"),(12,"GPIO19"),(13,"GPIO18"),(14,"GND"),(15,"3V3"),(16,"3V3")):add("U2 MCP3208",pin,net)
    for part,n1,n2,val in (("Riso","OUT","ADC_CH0","100 Ω"),("RmidH","3V3","MID","100 kΩ"),("RmidL","MID","GND","100 kΩ"),("Cmid","MID","GND","100 nF"),("Cop","3V3","GND","100 nF junto de U1.8/4"),("Cadc","3V3","GND","100 nF junto de U2.16/14"),("Cref","3V3","GND","100 nF junto de U2.15/14"),("Rcs","GPIO27","3V3","10 kΩ")):
        add(part,1,n1,val);add(part,2,n2,val)
    for part in ("D1 BPW34","D2 BPW34"):add(part,"A","GND");add(part,"K","SUM")
    with (OUT/"conexoes_comuns.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    common=list(rows)
    for part,value in (("Rf1","470 kΩ"),("Rf2","470 kΩ"),("Cf","8,2 pF C0G")):
        add(part,1,"OUT",value);add(part,2,"SUM",value)
    with (OUT/"conexoes_A_fixo.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    rows=common
    for part,value in (("Rbase","470 kΩ"),("Cbase","4,7 pF C0G")):
        add(part,1,"OUT",value);add(part,2,"SUM",value)
    for i,(res,cap) in enumerate((("52,3 kΩ","3,3 pF"),("127 kΩ","1,0 pF"),("412 kΩ","1,0 pF"))):
        for part,value in ((f"R{i}",res),(f"C{i}",cap+" C0G")):
            add(part,1,"SUM",value);add(part,2,f"X{i}",value)
    for pin,net in ((1,"OUT"),(2,"X0"),(3,"X1"),(4,"OUT"),(5,"CTRL1"),(6,"CTRL2"),(7,"GND"),
                    (8,"OUT"),(9,"X2"),(10,"GND"),(11,"GND"),(12,"GND"),(13,"CTRL0"),(14,"3V3")):
        add("U3 CD4066BE",pin,net)
    for i,gpio in enumerate((32,33,26)):
        add(f"Rctrl{i}",1,f"GPIO{gpio}","330 Ω");add(f"Rctrl{i}",2,f"CTRL{i}","330 Ω")
        add(f"Rpd{i}",1,f"CTRL{i}","100 kΩ");add(f"Rpd{i}",2,"GND","100 kΩ")
    add("C4066",1,"3V3","100 nF junto de U3.14/7");add("C4066",2,"GND","100 nF")
    with (OUT/"conexoes_B_autoranging.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    adc();follower();tia();ranges();connections()
