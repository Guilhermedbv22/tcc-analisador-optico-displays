"""Build, smoke-test and package the Windows x64 distribution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from iris_desktop import __version__

RELEASE=ROOT/"dist-windows"


def find_iscc():
    override=os.environ.get("IRIS_ISCC")
    if override and Path(override).is_file():
        return Path(override)
    on_path=shutil.which("ISCC.exe")
    if on_path:
        return Path(on_path)
    for var in ("ProgramFiles(x86)","ProgramFiles","LOCALAPPDATA"):
        location=os.environ.get(var)
        if not location:
            continue
        for suffix in (Path("Inno Setup 6/ISCC.exe"),Path("Programs/Inno Setup 6/ISCC.exe")):
            candidate=Path(location)/suffix
            if candidate.is_file():
                return candidate
    raise SystemExit("Instale o Inno Setup 6 ou defina IRIS_ISCC com o caminho de ISCC.exe.")


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args],cwd=ROOT,check=True,**kwargs)


def write_metadata():
    parts=tuple(int(value) for value in __version__.split("."))+(0,)
    text=f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0,
      OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041604b0', [
      StringStruct('CompanyName', 'Projeto Íris'),
      StringStruct('FileDescription', 'Íris Desktop'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'IrisDesktop'),
      StringStruct('OriginalFilename', 'IrisDesktop.exe'),
      StringStruct('ProductName', 'Íris Desktop'),
      StringStruct('ProductVersion', '{__version__}')
  ])]), VarFileInfo([VarStruct('Translation', [1046, 1200])])]
)"""
    path=ROOT/"build"/"windows-version.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text,encoding="utf-8")


def create_portable(bundle):
    portable=RELEASE/f"IrisDesktop-Portable-{__version__}-x64.zip"
    instructions=("Extraia a pasta inteira e abra IrisDesktop.exe.\n"
                  "O histórico fica em %LOCALAPPDATA%\\IrisDesktop.\n"
                  "Ajuda: https://tcc-iris.netlify.app/download.html\n")
    with zipfile.ZipFile(portable,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path,Path("IrisDesktop")/path.relative_to(bundle))
        archive.writestr("IrisDesktop/LEIA_PRIMEIRO.txt",instructions)
    return portable


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--portable-only",action="store_true")
    args=parser.parse_args()
    if sys.platform!="win32" or struct.calcsize("P")!=8:
        raise SystemExit("Execute no Windows com Python 3.12 x64.")
    iscc=None if args.portable_only else find_iscc()
    RELEASE.mkdir(exist_ok=True)
    write_metadata()
    run([sys.executable,"-m","PyInstaller","--noconfirm","--clean","IrisDesktop.spec"])
    bundle=ROOT/"dist"/"IrisDesktop"
    executable=bundle/"IrisDesktop.exe"
    with TemporaryDirectory(prefix="iris-smoke-") as data:
        run([executable,"--smoke-test","--data-dir",data],timeout=60)
        if not (Path(data)/"iris.sqlite3").is_file():
            raise SystemExit("O pacote não concluiu o teste de inicialização.")
    files={"portable":create_portable(bundle)}
    if iscc:
        run([iscc,f"/DIrisVersion={__version__}",ROOT/"packaging"/"IrisDesktop.iss"])
        files["installer"]=RELEASE/f"IrisDesktop-Setup-{__version__}-x64.exe"
        if files["installer"].read_bytes()[:2]!=b"MZ":
            raise SystemExit("Instalador inválido.")
    manifest={"version":__version__,"files":{
        key:{"name":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
        for key,path in files.items()
    }}
    (RELEASE/"releases.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
    print("Distribuição disponível em",RELEASE)


if __name__=="__main__":
    main()
