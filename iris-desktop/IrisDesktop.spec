# Use packaging/build_windows.py or gerar_distribuicao_windows.bat.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
build_metadata = root / "build" / "windows-version.txt"
analysis = Analysis(
    [str(root/"run_iris.py")], pathex=[str(root)],
    datas=[
        (str(root/"iris_desktop/assets"), "iris_desktop/assets"),
        (str(root/"docs"), "docs"),
    ] + collect_data_files("pyqtgraph"),
    hiddenimports=["matplotlib.backends.backend_agg","serial.tools.list_ports_windows"],
    excludes=["PyQt5","PyQt6","PySide2","tkinter","pytest","IPython","notebook"],
    hooksconfig={"matplotlib":{"backends":["Agg"]}},
)
bytecode = PYZ(analysis.pure)
application = EXE(
    bytecode, analysis.scripts, [], exclude_binaries=True, name="IrisDesktop",
    icon=str(root/"iris_desktop/assets/iris.ico"),
    version=str(build_metadata) if build_metadata.is_file() else None,
    console=False, upx=False,
)
bundle = COLLECT(application, analysis.binaries, analysis.datas, strip=False, upx=False, name="IrisDesktop")
