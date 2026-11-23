# PyInstaller spec for LocalWrite.  Build with:  build_exe.bat
# Produces a one-folder app (fast start-up) in dist\LocalWrite\LocalWrite.exe
from pathlib import Path

ROOT = Path(SPECPATH)

# Qt modules LocalWrite does not use - excluding them keeps the bundle small.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtXml",
    "tkinter", "unittest", "pytest",
]

a = Analysis(
    [str(ROOT / "launch.pyw")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "resources"), "resources")],
    hiddenimports=["PySide6.QtNetwork"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalWrite",
    console=False,
    icon=str(ROOT / "resources" / "icons" / "app.ico"),
    version=None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalWrite", upx=False)
