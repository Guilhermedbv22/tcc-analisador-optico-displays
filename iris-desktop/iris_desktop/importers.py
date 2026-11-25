"""Importação dos ensaios v4/CIA e CSV do voltímetro; sem inferir montagem por nome."""
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile
from collections import defaultdict
from datetime import datetime
import numpy as np
from .analysis import analyze
from .config import TestConfig
from .core.protocolo import Captura


def old_config(value):
    mapping = {"rotulo":"title", "hz":"refresh_hz", "brilho":"brightness", "contraste":"contrast",
               "v_opamp":"supply_v", "taxa":"rate_sps", "janela":"window_ms", "pre":"pre_ms",
               "matriz":"levels", "repeticoes":"repetitions", "posicao":"sensor_position",
               "mediana":"median_samples", "spi":"spi_hz", "warmup":"warmup_min", "divisor_k":"attenuation_k",
               "display":"screen","semente":"seed","ordem_aleatoria":"randomize","fundo":"background_rgb","pares":"custom_pairs"}
    out = {mapping.get(k,k):v for k,v in value.items()}
    # Não identificar o amplificador como MCP6022 apenas por ser o padrão da interface.
    for k in ("monitor", "amplifier", "assembly", "ambient", "resolution", "hdr", "vrr"):
        out.setdefault(k, "")
    c = TestConfig.from_dict(out)
    if c.custom_pairs:c.custom_pairs=c.custom_pairs.replace(":",">")
    # Defaults da tela de um NOVO ensaio não são evidência de condições antigas.
    for key in ("vref","supply_v","rf_kohm","cf_pf","attenuation_k","rate_sps","window_ms",
                "pre_ms","hold_ms","spi_hz","levels","repetitions","warmup_min","refresh_hz",
                "screen","full_screen","patch_percent","background_rgb","seed","randomize"):
        if key not in out:setattr(c,key,None)
    if "patch" in value and not value.get("patch_10pct",False):c.patch_pixels=int(value["patch"])
    if "intervalo" in value:c.hold_ms=round(float(value["intervalo"])*1000)
    if "referencias_antes" in value and "referencias_depois" in value:
        c.static_references=bool(value["referencias_antes"] and value["referencias_depois"])
    if "mediana" in value:
        c.criteria["mediana_amostras"] = int(value["mediana"])
    for old, new in (("patamar_inicial", "patamar_inicial_ms"), ("patamar_final", "patamar_final_ms"),
                     ("snr_minimo", "snr_minimo"), ("amplitude_minima", "amplitude_minima"),
                     ("persistencia", "persistencia_ms"), ("permanencia", "permanencia_final_ms")):
        if old in value:
            c.criteria[new] = float(value[old])
    if "tolerancia" in value:
        c.criteria["tolerancia_acomodacao"] = float(value["tolerancia"])/100
    c.notes = str(value.get("notas", "")) + "\nImportado: identificação original mantida; conferir condições ausentes."
    return c


class Source:
    def __init__(self, path):
        self.path = Path(path)
        self.zip = None
        if self.path.suffix.lower() == ".zip":
            self.zip = zipfile.ZipFile(self.path)
            if sum(i.file_size for i in self.zip.infolist()) > 512*1024**2:
                self.zip.close()
                raise ValueError("ZIP excede 512 MB descompactados. Importe as sessões separadamente.")
            self.names = set(self.zip.namelist())
        else:
            self.root = (self.path if self.path.is_dir() else self.path.parent).resolve()
            self.names = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}

    def read(self, name):
        pure = PurePosixPath(str(name).replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("Caminho inválido no arquivo de importação.")
        if self.zip:
            return self.zip.read(str(pure))
        real = (self.root / str(pure)).resolve()
        if not real.is_relative_to(self.root):
            raise ValueError("Arquivo aponta para fora da sessão.")
        return real.read_bytes()

    def close(self):
        if self.zip:
            self.zip.close()


def read_capture(data, meta):
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if ";" in text.splitlines()[0] else ",")
    rows = list(reader)
    if not rows:
        raise ValueError("CSV sem amostras.")
    if "tempo_us" in rows[0]:
        t = np.array([float(r["tempo_us"]) for r in rows])
    elif "tempo_ms" in rows[0]:
        t = np.array([float(r["tempo_ms"])*1000 for r in rows])
        meta["legacy"] = True
    else:
        raise ValueError("CSV sem coluna de tempo; não inventar timestamps.")
    y = np.array([float(r["adc_bruto"]) for r in rows])
    if "leitura_us" in rows[0]:
        duration = np.array([float(r["leitura_us"]) for r in rows])
    else:
        duration = np.ones(len(y))
        meta["legacy"] = True
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(duration)):
        raise ValueError("Há amostras não finitas no CSV.")
    return Captura(t, y, duration, meta)


def import_monitor(store, path):
    source = Source(path)
    imported = []
    try:
        manifests = sorted(n for n in source.names if PurePosixPath(n).name in ("ensaio.json", "sessao.json"))
        if not manifests:
            raise ValueError("Não encontrei ensaio.json ou sessao.json. Selecione o ZIP ou a pasta original completa.")
        with store.db() as db:
            previous = [json.loads(r[0]).get("manifest_sha256") for r in db.execute("SELECT provenance FROM sessions")]
        for manifest in manifests:
            data = source.read(manifest)
            digest = hashlib.sha256(data).hexdigest()
            if digest in previous:
                continue
            previous.append(digest)
            info = json.loads(data)
            cfg = old_config(info.get("config", info))
            cfg.notes += "\nManifesto original: " + manifest
            sim = "SIMULA" in str(info.get("tipo", "")).upper()
            sid = store.session(cfg.title or "Importação de ensaio", cfg.to_dict(),
                provenance={"source":str(path), "manifest":manifest, "manifest_sha256":digest,
                            "original":info, "identification":"Conferir identificação original; não inferida pelo nome."}, simulation=sim)
            base = str(PurePosixPath(manifest).parent)
            base = "" if base == "." else base + "/"
            captures = info.get("capturas")
            if captures is None:
                captures = []
                for name in sorted(source.names):
                    if name.startswith(base+"capturas/") and name.endswith(".json"):
                        side = json.loads(source.read(name))
                        row = side.get("resultado", side)
                        row = dict(row, meta=side.get("meta", row.get("meta", {})))
                        row["arquivo"] = name[len(base):-5]+".csv"
                        captures.append(row)
            count, failures = 0, 0
            for item in captures:
                try:
                    rel = item["arquivo"]
                    if not rel.endswith(".csv"):
                        rel += ".csv"
                    cap = read_capture(source.read(base+rel), dict(item.get("meta", {})))
                    wire = base + rel[:-4] + ".bin"
                    if wire in source.names:
                        cap.wire = source.read(wire)
                    a = int(item.get("origem", item.get("origem_rgb", 0)))
                    b = int(item.get("destino", item.get("destino_rgb", 0)))
                    stage = item.get("etapa", "transicao")
                    task = dict(origin=a, destination=b, repetition=int(item.get("repeticao", 1)),
                                phase="medicao" if stage == "transicao" else stage)
                    cid = store.save_capture(sid, cap, task)
                    original = item.get("resultados", {})
                    if original:
                        for mode, result in original.items():
                            if isinstance(result, dict):
                                store.save_analysis(cid, dict(result, desktop_version=f"original/{mode}"))
                    elif "valida" in item:
                        store.save_analysis(cid, dict(item, desktop_version="original/legado"))
                    store.save_analysis(cid, analyze(cap, a, b, cfg.get_criteria()))
                    count += 1
                except Exception as exc:
                    failures += 1
                    store.event(sid, "importacao_incompleta", {"capture":item.get("arquivo"),"error":str(exc)})
            store.finish(sid, "importada" if not failures else "importada_com_falhas")
            imported.append(dict(session_id=sid, captures=count, failures=failures, simulation=sim))
    finally:
        source.close()
    return imported


def import_bench_csv(store, path):
    data = Path(path).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(data), delimiter=";" if ";" in data.splitlines()[0] else ","))
    if not rows:
        raise ValueError("CSV de bancada vazio.")
    if "media_64_codigos" not in rows[0] and "mean_raw" not in rows[0]:
        raise ValueError("CSV não é do voltímetro Íris.")
    # O CSV anterior pode conter vários componentes e níveis. Não misturar seus
    # pontos numa média de ruído nem subtrair saída de uma condição da entrada de outra.
    groups=defaultdict(list)
    for row in rows:groups[row.get("rotulo") or Path(path).stem].append(row)
    imported=[]
    for title,group in groups.items():
        sources={json.loads(r["payload"]).get("source","Não informado") if r.get("payload") else
                 "MCP3208" if "media_64_codigos" in r else r.get("source","Não informado") for r in group}
        sid = store.session(title, {"source_file":str(path), "identification":"Rótulos originais; conferir montagem e CH0 ligado ao GND.","adc":next(iter(sources)) if len(sources)==1 else "Fontes mistas"},
                            kind="bancada", provenance={"sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),"original_label":title})
        first=None
        for index, row in enumerate(group):
            def val(*names):
                for name in names:
                    if row.get(name) not in (None, ""):
                        return float(row[name])
                return None
            if row.get("payload"):
                payload=json.loads(row["payload"])
                if not isinstance(payload,dict):raise ValueError("Payload de bancada precisa ser JSON de objeto.")
            else:
                payload = dict(source="MCP3208" if "media_64_codigos" in row else row.get("source","Não informado"),
                               mean_raw=val("media_64_codigos", "mean_raw"),
                               min_raw=val("min_64_codigos", "min_raw"), max_raw=val("max_64_codigos", "max_raw"),
                               std_raw=val("std_raw"), original=row)
            elapsed=val("elapsed_s")
            if elapsed is None and row.get("instante_utc"):
                instant=datetime.fromisoformat(row["instante_utc"])
                first=first or instant
                elapsed=(instant-first).total_seconds()
            if elapsed is None:
                elapsed=index;payload["elapsed_basis"]="índice do registro; tempo não disponível"
            store.bench_add(sid, elapsed,int(row.get("canal", row.get("channel", 0))), payload, val("vref_informada_V", "vref") or 3.3)
        store.finish(sid, "importada")
        imported.append(dict(session_id=sid,readings=len(group),label=title))
    return imported


def import_native_session(store, path):
    """ZIP de exportação Desktop 1.0: também verifica hashes e retém revisões."""
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 512*1024**2:
            raise ValueError("ZIP excede 512 MB.")
        info = json.loads(z.read("export.json"))
        session = info["session"]
        sid = store.session(session["title"], session["config"], session["kind"],
                            provenance={"native_import":str(path), "original":session}, simulation=session["simulation"])
        names=set(z.namelist())
        for row in info.get("captures", []):
            raw_path=row["raw_file"]
            normalized=raw_path.replace(chr(92),"/")
            member=normalized if normalized in names else raw_path
            raw = z.read(member)
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("ZIP contém raw alterado; SHA-256 não confere.")
            with np.load(io.BytesIO(raw), allow_pickle=False) as n:
                cap = Captura(n["t_us"].copy(), n["adc"].copy(), n["leitura_us"].copy(), row["meta"])
            wire_path = str(PurePosixPath(member).with_suffix(".wire"))
            if wire_path in names:
                cap.wire = z.read(wire_path)
            cid = store.save_capture(sid, cap, row["meta"]["task"])
            for revision in row["revisions"]:
                store.save_analysis(cid, json.loads(revision["result"]))
        for row in info.get("bench", []):
            store.bench_add(sid, row["elapsed_s"], row["channel"], json.loads(row["payload"]), row["vref"])
        for event in info.get("events", []):
            store.event(sid, event["type"], event["payload"])
        store.finish(sid, "importada")
        return sid


def import_report_export(store, path):
    """Lê dados/sessao_exportada.json + resultados.csv + amostras de um relatório.

    Preserva os resultados exportados: reproduzir um ensaio não é uma nova coleta
    nem uma reanálise com critérios diferentes.
    """
    source=Source(path);out=[]
    try:
        manifests=sorted(n for n in source.names if PurePosixPath(n).name=='sessao_exportada.json')
        if not manifests:raise ValueError('Não encontrei sessao_exportada.json no relatório.')
        for manifest in manifests:
            raw=source.read(manifest);digest=hashlib.sha256(raw).hexdigest()
            with store.db() as db:
                previous=[json.loads(row[0]).get('report_sha256') for row in db.execute('SELECT provenance FROM sessions')]
            if digest in previous:continue
            info=json.loads(raw);base=str(PurePosixPath(manifest).parent)
            base='' if base=='.' else base+'/'
            text=source.read(base+'resultados.csv').decode('utf-8-sig')
            delimiter=';' if ';' in text.splitlines()[0] else ','
            rows=list(csv.DictReader(io.StringIO(text),delimiter=delimiter))
            sid=store.session(info.get('title','Ensaio exportado'),info.get('config',{}),
                provenance={'source':str(path),'report_sha256':digest,'original':info,'results':'Resultados originais do relatório; sem nova aquisição.'},
                simulation=bool(info.get('simulation',False)))
            available=defaultdict(list)
            for name in sorted(source.names):
                if not name.startswith(base+'amostras/'):continue
                match=re.search(r'_(\d+)_(\d+)_r(\d+)\.csv$',name)
                if match:available[tuple(map(int,match.groups()))].append(name)
            count=0;failures=0
            for row in rows:
                try:
                    def decode(v):
                        if v is None or v=='':return None
                        if v=='True':return True
                        if v=='False':return False
                        try:return json.loads(v)
                        except (ValueError,TypeError):return v
                    result={k:decode(v) for k,v in row.items()}
                    a,b=int(result['origem_rgb']),int(result['destino_rgb'])
                    rep=int(result.get('repetition') or result.get('repeticao') or 1)
                    names=available[(a,b,rep)]
                    if not names:raise ValueError(f'Sem amostras exportadas para {a} → {b}, r{rep}.')
                    name=names.pop(0);cap=read_capture(source.read(name),dict(result.get('meta') or {}))
                    result['desktop_version']=result.get('analysis_version') or result.get('desktop_version') or 'original/relatorio'
                    task=dict(origin=a,destination=b,repetition=rep,phase=result.get('phase') or 'medicao')
                    store.save_capture(sid,cap,task,result);count+=1
                except Exception as exc:
                    failures+=1;store.event(sid,'importacao_incompleta',{'error':str(exc),'row':row.get('capture_id')})
            store.finish(sid,'importada' if not failures else 'importada_com_falhas')
            out.append(dict(session_id=sid,captures=count,failures=failures,simulation=bool(info.get('simulation',False))))
        return out
    finally:source.close()


def import_recording(store,path):
    """Seleciona o formato sem exigir nenhum dispositivo serial."""
    path=Path(path)
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as archive:
            names=archive.namelist()
            if 'export.json' in names:return import_native_session(store,path)
            if any(PurePosixPath(n).name=='sessao_exportada.json' for n in names):
                return import_report_export(store,path)
    else:
        root=path if path.is_dir() else path.parent
        if any(root.rglob('sessao_exportada.json')):return import_report_export(store,path)
    return import_monitor(store,path)
