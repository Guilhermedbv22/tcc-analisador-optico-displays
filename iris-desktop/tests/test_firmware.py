import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import pytest
from iris_desktop.core.protocolo import Dispositivo

ROOT=Path(__file__).parents[1]

@pytest.fixture(scope="module")
def firmware_binary(tmp_path_factory):
    if os.name=="nt":pytest.skip("Harness com pipe POSIX; compilação Arduino é separada")
    if not shutil.which("g++"):pytest.skip("g++ indisponível para o teste de periféricos falsos")
    path=tmp_path_factory.mktemp("firmware")/"firmware_host"
    subprocess.run(["g++","-std=c++17","-DCONFIG_IDF_TARGET_ESP32=1","-I",str(ROOT/"tests/firmware_stubs"),str(ROOT/"tests/firmware_host.cpp"),"-o",str(path)],check=True,capture_output=True)
    return path

class ProcessTransport:
    def __init__(self,binary):
        self.p=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def write(self,data):return self.p.stdin.write(data)
    def flush(self):self.p.stdin.flush()
    def read(self,n):
        if select.select([self.p.stdout],[],[],.02)[0]:return os.read(self.p.stdout.fileno(),n)
        return b""
    def close(self):
        self.p.stdin.close();self.p.terminate();self.p.wait(timeout=3)

def test_real_firmware_wire_parser(firmware_binary):
    d=Dispositivo("host",transporte=ProcessTransport(firmware_binary))
    try:
        assert d.hello["fw"]=="4.1.0" and "gain4" in d.hello["features"]
        d.configurar("MCP3208",100,300,7)
        st=d.estatica();assert st["channel"]==7 and st["n"]==64 and st["std_raw"]==0
        assert len(st["raw_codes64"])==64 and all(v==1234 for v in st["raw_codes64"])
        assert len(st["t_us64"])==64 and st["t_us64"][-1]>st["t_us64"][0]
        assert all(v>0 for v in st["read_us64"])
        cap=d.capturar();assert len(cap.adc)==3000 and cap.meta["channel"]==7
        assert not cap.meta["gain_enabled"] and all(cap.adc==1234)
        gain=json.loads(d.comando("GAIN ENABLE 1","GAIN ")[5:]);assert gain["enabled"] and gain["range"]==0
        d.comando("GAIN SET 2","GAIN ");cap=d.capturar()
        assert cap.meta["gain_range"]==2 and cap.meta["gain_enabled"]
        d.comando("AUTO START 800","AUTO ");d.capturar()
        # Periférico falso retorna código constante: zero de amplitude, não autoaprovar.
        out=json.loads(d.comando("AUTO EVAL","AUTO ")[5:]);assert out["status"]=="NO_SIGNAL"
    finally:d.fechar()

def test_gain_state_peak_headroom_and_fallback(tmp_path):
    if not shutil.which("g++"):pytest.skip("g++ indisponível")
    code=tmp_path/"g.cpp";binary=tmp_path/"g"
    code.write_text(r'''
    #include <cassert>
    #include "gain_logic.h"
    using namespace IrisGain;
    int main(){
      Auto a;a.start(800);assert(a.evaluate()==Decision::NO_CAPTURES);
      a.observe(100,1200);assert(a.evaluate()==Decision::TRY_NEXT && a.range==1);
      a.observe(100,2500);assert(a.evaluate()==Decision::TRY_NEXT && a.range==2);
      a.observe(100,3600);assert(a.evaluate()==Decision::LOCKED && a.range==1);
      a.start(800);a.observe(100,3900);assert(a.evaluate()==Decision::OUT_OF_RANGE);
      a.start(800);a.observe(0,0);assert(a.evaluate()==Decision::NO_SIGNAL);
      a.start(800);for(int i=0;i<3;++i){a.observe(200,1000);assert(a.evaluate()==Decision::TRY_NEXT);}
      a.observe(200,1000);assert(a.evaluate()==Decision::LOCKED && a.range==3);
      assert(effective(0)>47000 && effective(0)<47100);
      assert(effective(1)>99000 && effective(1)<100100);
      assert(effective(2)>219000 && effective(2)<221000);
      assert(effective(0,2000)>effective(0));
    }''')
    subprocess.run(["g++","-std=c++17","-I",str(ROOT/"firmware/iris_esp32"),str(code),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

def test_actual_pyserial_qthread_against_firmware_over_pty(firmware_binary,qapp):
    if os.name!="posix":pytest.skip("PTY POSIX")
    import threading
    import tty
    from PySide6.QtTest import QTest
    from iris_desktop.device import DeviceClient
    master,slave=os.openpty();tty.setraw(slave);port=os.ttyname(slave)
    proc=subprocess.Popen([str(firmware_binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    stop=threading.Event()
    def bridge():
        try:
            while not stop.is_set():
                ready,_,_=select.select([master,proc.stdout],[],[],.02)
                if master in ready:
                    data=os.read(master,4096)
                    if data:proc.stdin.write(data);proc.stdin.flush()
                if proc.stdout in ready:
                    data=os.read(proc.stdout.fileno(),4096)
                    if data:os.write(master,data)
        except (OSError,BrokenPipeError):pass
    thread=threading.Thread(target=bridge,daemon=True);thread.start()
    device=DeviceClient();results={};errors=[]
    device.result.connect(lambda i,k,r:results.update({i:r}));device.error.connect(lambda *e:errors.append(e))
    def request(kind,data=None):
        i=device.submit(kind,data);deadline=time.monotonic()+6
        while time.monotonic()<deadline and i not in results and not errors:qapp.processEvents();QTest.qWait(5)
        assert not errors and i in results
        return results[i]
    try:
        assert request("connect",{"port":port})["protocol"]==4
        request("configure",dict(fonte="MCP3208",periodo_us=100,janela_ms=300,canal=3,spi_hz=1000000))
        assert request("stat",dict(source="MCP3208",channel=3))["mean_raw"]==1234
        cap=request("capture");assert cap.meta["channel"]==3 and len(cap.adc)==3000 and cap.wire
        request("command",dict(command="GAIN ENABLE 1",prefix="GAIN "))
        request("command",dict(command="AUTO START 800",prefix="AUTO "))
        request("disconnect")
        request("connect",{"port":port})
        state=request("command",dict(command="GAIN?",prefix="GAIN "))
        assert not state["auto_active"] and state["range"]==0 and state["enabled"]
        request("disconnect");assert not device.connected
    finally:
        device.shutdown();device.worker.wait(3000);stop.set();thread.join(1)
        proc.terminate();proc.wait(timeout=3);os.close(master);os.close(slave)
