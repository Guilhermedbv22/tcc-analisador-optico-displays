"""Compatibilidade de importação com relatórios da versão anterior."""
from pathlib import Path
import csv,io,json,time,zipfile
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from iris_desktop.importers import import_recording,import_report_export
from iris_desktop.storage import Store

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def recording(tmp_path,sample_path):
    s=Store(tmp_path)
    result=import_recording(s,sample_path('Relatorio_LG_Legado.zip'))
    assert result[0]['captures']==30 and result[0]['failures']==0
    return s,result[0]['session_id']


def test_report_import_preserves_values_and_is_idempotent(recording,sample_path):
    s,sid=recording
    with zipfile.ZipFile(sample_path('Relatorio_LG_Legado.zip')) as z:
        name=next(n for n in z.namelist() if n.endswith('resultados.csv'))
        originals=list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig'))))
    rows=s.rows(sid,False)
    assert len(rows)==len(originals)==30
    for old,new in zip(originals,rows):
        assert new['g2g_ms']==float(old['g2g_ms'])
        assert new['overshoot_pct']==float(old['overshoot_pct'])
        assert new['valida']==(old['valida']=='True')
    assert s.get_session(sid)['config']['overdrive']==''
    assert import_report_export(s,sample_path('Relatorio_LG_Legado.zip'))==[]
    assert len(s.sessions())==1

