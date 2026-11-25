import argparse
import os
from pathlib import Path
import sys
from . import __version__


def data_dir():
    if sys.platform=="win32":return Path(os.environ.get("LOCALAPPDATA",Path.home()/"AppData"/"Local"))/"IrisDesktop"
    return Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local"/"share"))/"IrisDesktop"


def main():
    parser=argparse.ArgumentParser(description=f"Íris Desktop {__version__}")
    parser.add_argument("--data-dir",type=Path,default=data_dir(),help="Pasta do SQLite e dos dados brutos")
    parser.add_argument("--import",dest="import_path",type=Path,help="Importar ensaio antigo ou sessão nativa ao abrir")
    parser.add_argument("--version",action="version",version=__version__)
    parser.add_argument("--smoke-test",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    from PySide6.QtWidgets import QApplication
    from .storage import Store
    from .ui.window import MainWindow
    app=QApplication(sys.argv[:1]);app.setApplicationName("Íris Desktop");app.setOrganizationName("Íris");app.setApplicationVersion(__version__)
    window=MainWindow(Store(args.data_dir));window.show()
    if args.smoke_test:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300,window.close)
    if args.import_path:window.guard(lambda:window.import_path(args.import_path))
    return app.exec()


if __name__=="__main__":raise SystemExit(main())
