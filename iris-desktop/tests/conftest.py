import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import pytest
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sample_path():
    """Optional archive of historical measurements, kept outside release ZIPs."""
    from pathlib import Path
    root=Path(os.environ.get("IRIS_TEST_DATA",Path(__file__).resolve().parents[1]/"examples"))
    def resolve(name):
        path=root/name
        if not path.is_file():
            pytest.skip("Arquivo experimental opcional. Consulte IRIS_TEST_DATA.")
        return path
    return resolve
