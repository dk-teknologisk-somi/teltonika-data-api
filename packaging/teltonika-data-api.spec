# PyInstaller build spec, used by scripts/build_linux.sh and scripts/build_windows.bat.
# Build on the target OS (no cross-compilation). Run from the project root:
#   pyinstaller packaging/teltonika-data-api.spec
# Result: dist/teltonika-data-api (Linux) or dist/teltonika-data-api.exe (Windows)

import os

a = Analysis([os.path.join(SPECPATH, "..", "src", "main.py")])
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    # The onefile parent process would otherwise forward Ctrl+C a second time,
    # interrupting uvicorn's graceful shutdown.
    [("pyi-bootloader-ignore-signals", None, "OPTION")],
    name="teltonika-data-api",
    console=True,
    upx=False,
)
