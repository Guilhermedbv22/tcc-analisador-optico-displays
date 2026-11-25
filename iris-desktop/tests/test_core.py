from dataclasses import replace
from pathlib import Path
import hashlib
import json
import zlib
import numpy as np
import pytest
from iris_desktop.core.protocolo import REGISTRO,Captura,validar_payload,ErroProtocolo,validar_configuracao
from iris_desktop.core.nucleo import Criterios
from iris_desktop.analysis import analyze,curve
from iris_desktop.config import TestConfig,comparison_conditions
from iris_desktop.device import synthetic_capture

@pytest.mark.parametrize("a,b",[(0,255),(255,0),(51,102),(204,102)])
def test_response_both_directions(a,b):
    r=analyze(synthetic_capture(a,b),a,b)
    assert r["valida"] and 4.8<r["g2g_ms"]<5.4
    assert r["acomodacao_ms"]>r["g2g_ms"]
    assert 5<r["overshoot_pct"]<7
    assert r["undershoot_pct"]==(r["overshoot_pct"] if a>b else 0)

@pytest.mark.parametrize("value,state",[(0,"zero_continuo"),(1900,"codigo_constante"),(4095,"codigo_constante")])
def test_constant_is_not_zero_ms(value,state):
    c=synthetic_capture();c.adc[:]=value
    r=analyze(c,0,255)
    assert r["health"]["transport_ok"]
    assert not r["valida"] and r["g2g_ms"] is None and state in r["motivos"]

def test_ground_static_allowed_as_data():
    c=synthetic_capture();c.adc[:]=0
    r=analyze(c,0,0)
    assert r["status"]=="ESTATICA" and "pode ser correto" in r["health"]["message"]

def packet():
    c=synthetic_capture();a=np.zeros(len(c.adc),dtype=REGISTRO)
    a["t_us"]=c.t_us;a["adc"]=c.adc;a["leitura_us"]=c.leitura_us
    meta={**c.meta,"id":7};payload=a.tobytes()
    return meta,payload,f"END 7 {zlib.crc32(payload):08X}"

def test_crc_rejects_corruption():
    m,p,e=packet();assert len(validar_payload(m,p,e,7).adc)==3000
    with pytest.raises(ErroProtocolo):validar_payload(m,p[:-1]+bytes([p[-1]^1]),e,7)
    with pytest.raises(ErroProtocolo):validar_payload(m,p[:-8],e,7)
    with pytest.raises(ErroProtocolo):validar_payload(m,p,e,8)

def test_zero_payload_is_structurally_valid():
    m,p,e=packet();a=np.frombuffer(p,dtype=REGISTRO).copy();a["adc"]=0;p=a.tobytes()
    c=validar_payload(m,p,f"END 7 {zlib.crc32(p):08X}",7)
    assert not analyze(c,0,255)["valida"]

@pytest.mark.parametrize("changes",[{"missed":1},{"period_us":200}])
def test_timing_rejected(changes):
    c=synthetic_capture();c.meta.update(changes)
    assert "temporizacao_irregular" in analyze(c,0,255)["motivos"]

def test_filter_sensitivity_and_raw_immutable():
    c=synthetic_capture();original=c.adc.copy();c.adc[850]=4000
    a=analyze(c,0,255,Criterios(mediana_amostras=1));b=analyze(c,0,255,Criterios(mediana_amostras=3))
    assert a["overshoot_pct"]>b["overshoot_pct"]+10
    assert c.adc[850]==4000

def test_config_contract():
    c=TestConfig();assert len(c.tasks())==30
    c.levels=5;c.repetitions=3;assert len(c.tasks())==60
    c.custom_pairs="0>255, 255>0";assert len(c.tasks())==6
    c.criteria["mediana_amostras"]=2
    with pytest.raises(ValueError):c.validate()
    with pytest.raises(ValueError):validar_configuracao("MCP3208",50,300,0,500000)
    with pytest.raises(ValueError):validar_configuracao("INTERNO",100,300,1)
    with pytest.raises(ValueError,match="proteção física"):TestConfig(supply_v=5.0).validate()
    assert TestConfig(supply_v=5.0,attenuation_k=.6).validate()

def test_internal_not_converted_by_nominal_vref():
    c=synthetic_capture();c.meta["source"]="INTERNO";r=analyze(c,0,255)
    with pytest.raises(ValueError):curve(c,r,unit="V")

def test_matched_conditions_do_not_blame_adc():
    a=TestConfig().to_dict();b={**a,"adc":"INTERNO","rf_kohm":470,"amplifier":"MCP6002"}
    diff,unknown=comparison_conditions(a,b,"ADC")
    assert "rf_kohm" in diff and "amplifier" in diff and "adc" not in diff
    assert "monitor" in unknown

def test_reused_source_hashes():
    root=Path(__file__).parents[1]
    for entry in json.loads((root/"docs/PROVENIENCIA.json").read_text()):
        assert hashlib.sha256((root/entry["destination"]).read_bytes()).hexdigest()==entry.get("sha256_atual",entry["sha256_original"])
