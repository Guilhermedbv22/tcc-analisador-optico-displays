"""SQLite indexa metadados e revisões. Amostras originais nunca são sobrescritas."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import uuid
import numpy as np
from .core.protocolo import Captura


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def json_text(value):
    def default(x):
        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, Path):
            return str(x)
        raise TypeError(type(x).__name__)
    return json.dumps(value, ensure_ascii=False, default=default, allow_nan=False)


def atomic(path, data):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "iris.sqlite3"
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_info(version INTEGER NOT NULL);
            INSERT INTO schema_info SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_info);
            CREATE TABLE IF NOT EXISTS sessions(
              id TEXT PRIMARY KEY, created TEXT NOT NULL, kind TEXT NOT NULL,
              title TEXT NOT NULL, status TEXT NOT NULL, config TEXT NOT NULL,
              provenance TEXT NOT NULL, simulation INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS captures(
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
              created TEXT NOT NULL, origin INTEGER, destination INTEGER, repetition INTEGER,
              phase TEXT NOT NULL, raw_file TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
              meta TEXT NOT NULL, analysis_error TEXT);
            CREATE TABLE IF NOT EXISTS analyses(
              id INTEGER PRIMARY KEY AUTOINCREMENT, capture_id INTEGER NOT NULL REFERENCES captures(id),
              created TEXT NOT NULL, version TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bench(
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
              created TEXT NOT NULL, elapsed_s REAL NOT NULL, channel INTEGER NOT NULL,
              mean_raw REAL NOT NULL, min_raw REAL, max_raw REAL, std_raw REAL,
              vref REAL NOT NULL, value_v REAL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT REFERENCES sessions(id),
              created TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS capture_session ON captures(session_id);
            CREATE INDEX IF NOT EXISTS analysis_capture ON analyses(capture_id,id);
            CREATE INDEX IF NOT EXISTS bench_session ON bench(session_id,id);
            """)
            version = db.execute("SELECT version FROM schema_info").fetchone()[0]
            if version != 1:
                raise RuntimeError(f"Esquema SQLite {version} incompatível; não alterar este banco.")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def session(self, title, config, kind="monitor", provenance=None, simulation=False):
        sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        folder = self.root / "sessions" / sid
        folder.mkdir(parents=True)
        info = dict(id=sid, created=utc(), kind=kind, title=title, status="em_andamento",
                    config=config, provenance=provenance or {}, simulation=bool(simulation))
        atomic(folder / "session.json", json_text(info).encode("utf8"))
        with self.db() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)", (
                sid, info["created"], kind, title, info["status"], json_text(config),
                json_text(info["provenance"]), int(simulation)))
        return sid

    def finish(self, sid, status="concluida"):
        with self.db() as db:
            db.execute("UPDATE sessions SET status=? WHERE id=?", (status, sid))
        # O manifesto de sessão pode mudar de status; arquivos raw são imutáveis.
        info = self.get_session(sid)
        atomic(self.root / "sessions" / sid / "session.json", json_text(info).encode("utf8"))

    def get_session(self, sid):
        with self.db() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise KeyError(sid)
        result = dict(row)
        result["config"], result["provenance"] = json.loads(row["config"]), json.loads(row["provenance"])
        return result

    def sessions(self, query="", kind=None):
        with self.db() as db:
            rows = db.execute("SELECT * FROM sessions ORDER BY created DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if kind and item["kind"] != kind:
                continue
            if query.casefold() not in (item["title"]+" "+item["config"]+" "+item["id"]).casefold():
                continue
            item["config"] = json.loads(item["config"])
            result.append(item)
        return result

    def save_capture(self, sid, cap, task, result=None):
        # Cada captura ganha nome aleatório, criado com exclusividade (inclusive ao retomar).
        folder = self.root / "sessions" / sid / "raw"
        folder.mkdir(exist_ok=True)
        stem = uuid.uuid4().hex
        path = folder / (stem + ".npz")
        meta = {**cap.meta, "task": task}
        with path.open("xb") as stream:
            np.savez_compressed(stream, t_us=np.asarray(cap.t_us), adc=np.asarray(cap.adc),
                                leitura_us=np.asarray(cap.leitura_us))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        atomic(path.with_suffix(".json"), json_text(meta).encode("utf8"))
        if cap.wire:
            with path.with_suffix(".wire").open("xb") as stream:
                stream.write(cap.wire)
        with self.db() as db:
            cur = db.execute("INSERT INTO captures(session_id,created,origin,destination,repetition,phase,raw_file,sha256,meta) VALUES(?,?,?,?,?,?,?,?,?)",
                (sid, utc(), task.get("origin"), task.get("destination"), task.get("repetition", 1),
                 task.get("phase", "medicao"), str(path.relative_to(self.root)), digest, json_text(meta)))
            cid = cur.lastrowid
        if result is not None:
            self.save_analysis(cid, result)
        return cid

    def save_analysis(self, cid, result):
        with self.db() as db:
            db.execute("INSERT INTO analyses(capture_id,created,version,result) VALUES(?,?,?,?)",
                       (cid, utc(), result.get("desktop_version", result.get("versao", "desconhecida")), json_text(result)))

    def capture(self, cid, verify=True):
        with self.db() as db:
            row = db.execute("SELECT * FROM captures WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise KeyError(cid)
        path = (self.root / row["raw_file"]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Caminho raw fora do diretório de dados.")
        if verify and hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("O arquivo de aquisição mudou (SHA-256 divergente). Não reanalisar como original.")
        with np.load(path, allow_pickle=False) as raw:
            cap = Captura(raw["t_us"].copy(), raw["adc"].copy(), raw["leitura_us"].copy(), json.loads(row["meta"]))
        wire = path.with_suffix(".wire")
        cap.wire = wire.read_bytes() if wire.exists() else b""
        return cap

    def rows(self, sid, include_pilots=True):
        with self.db() as db:
            rows = db.execute("""SELECT c.*, a.result, a.id analysis_id, a.version analysis_version
                FROM captures c LEFT JOIN analyses a ON a.id=(SELECT MAX(id) FROM analyses WHERE capture_id=c.id)
                WHERE session_id=? ORDER BY c.id""", (sid,)).fetchall()
        out = []
        for row in rows:
            if not include_pilots and row["phase"] != "medicao":
                continue
            result = json.loads(row["result"]) if row["result"] else {}
            result.update(capture_id=row["id"], session_id=sid, phase=row["phase"],
                          repetition=row["repetition"], origem_rgb=row["origin"], destino_rgb=row["destination"],
                          raw_file=row["raw_file"], meta=json.loads(row["meta"]),
                          analysis_version=row["analysis_version"])
            out.append(result)
        return out

    def revisions(self, cid):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM analyses WHERE capture_id=? ORDER BY id", (cid,))]

    def event(self, sid, kind, payload):
        with self.db() as db:
            db.execute("INSERT INTO events(session_id,created,type,payload) VALUES(?,?,?,?)",
                       (sid, utc(), kind, json_text(payload)))

    def failure(self, sid, error, wire=b"", task=None):
        filename = None
        if wire:
            path = self.root / "sessions" / sid / ("falha_" + uuid.uuid4().hex + ".wire")
            path.write_bytes(wire)
            filename = str(path.relative_to(self.root))
        self.event(sid, "falha_aquisicao", dict(error=str(error), task=task, partial_wire=filename))

    def events(self, sid):
        with self.db() as db:
            return [dict(r, payload=json.loads(r["payload"])) for r in db.execute("SELECT * FROM events WHERE session_id=? ORDER BY id", (sid,))]

    def bench_add(self, sid, elapsed_s, channel, payload, vref):
        mean = float(payload["mean_raw"])
        if not np.isfinite(mean) or not 0 <= mean <= 4095:
            raise ValueError("STAT sem média válida de 12 bits.")
        volts = mean * vref / 4096 if payload.get("source") == "MCP3208" else None
        for key in ("min_raw", "max_raw", "std_raw"):
            value = payload.get(key)
            if value is not None and (not np.isfinite(value) or not 0 <= value <= 4095):
                raise ValueError(f"STAT inválido: {key}.")
        if payload.get("channel", channel) != channel:
            raise ValueError("Canal retornado pelo firmware diverge do solicitado.")
        lo,hi=payload.get("min_raw"),payload.get("max_raw")
        if (lo is not None and lo>mean) or (hi is not None and hi<mean):
            raise ValueError("Extremos de STAT incompatíveis com a média.")
        if "raw_codes64" in payload:
            codes=np.asarray(payload["raw_codes64"],float)
            times=np.asarray(payload.get("t_us64",[]),float)
            durations=np.asarray(payload.get("read_us64",[]),float)
            if (codes.shape!=(64,) or times.shape!=(64,) or durations.shape!=(64,) or
                not np.all(np.isfinite(codes)) or not np.all(np.isfinite(times)) or not np.all(np.isfinite(durations)) or
                np.any((codes<0)|(codes>4095)|(codes!=np.floor(codes))) or np.any(np.diff(times)<=0) or
                np.any(durations<=0) or abs(float(codes.mean())-mean)>.001):
                raise ValueError("Amostras individuais STAT inconsistentes; pacote não registrado como medição válida.")
        with self.db() as db:
            db.execute("INSERT INTO bench(session_id,created,elapsed_s,channel,mean_raw,min_raw,max_raw,std_raw,vref,value_v,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (sid, utc(), elapsed_s, channel, mean, payload.get("min_raw"), payload.get("max_raw"),
                 payload.get("std_raw"), vref, volts, json_text(payload)))
        return volts

    def bench_rows(self, sid):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM bench WHERE session_id=? ORDER BY id", (sid,))]

    def setting(self, key, default=None):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json_text(value)))

    def backup(self, destination):
        # snapshot consistente; copiar apenas o .sqlite3 aberto pode omitir o WAL.
        with self.db() as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
