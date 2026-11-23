# PyInstaller spec for LocalWrite.  Build with:  build_exe.bat
# Produces a one-folder app (fast start-up) in dist\LocalWrite\LocalWrite.exe
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH)
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "localwrite" / "__init__.py").read_text()).group(1)
_v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])

# Qt modules LocalWrite does not use, plus sqlite3: LocalWrite stores no history or database,
# so no database code should ever ship in the executable.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtXml",
    "PySide6.QtTest", "sqlite3", "_sqlite3", "tkinter", "unittest", "pytest", "localwrite.core.history",
]

VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "LocalWrite"),
            StringStruct("FileDescription", "LocalWrite - private local AI writing assistant"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("OriginalFilename", "LocalWrite.exe"),
            StringStruct("InternalName", "LocalWrite"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    version=VERSION_INFO,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LocalWrite", upx=False)
