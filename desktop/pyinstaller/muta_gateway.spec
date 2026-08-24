# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for the desktop gateway.

Tauri embeds the complete ``gateway/`` output. The ``_internal`` sibling directory is part
of the executable contract and must never be flattened or omitted.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPEC).resolve().parents[2]

datas = [
    (str(ROOT / "orchestrator" / "prompts"), "orchestrator/prompts"),
    (str(ROOT / "orchestrator" / "audio" / "audio.yaml"), "orchestrator/audio"),
    (
        str(ROOT / "orchestrator" / "exam" / "question_bank.json"),
        "orchestrator/exam",
    ),
]
binaries = []
hiddenimports = collect_submodules("uvicorn")

# PyInstaller's built-in matplotlib hook collects mpl-data and the selected Agg backend.
# collect_all(matplotlib) also drags its tests, Qt editor and docs into the product. Sherpa's
# wheel carries a platform-native extension/data closure and does require explicit collection.
package_datas, package_binaries, package_hidden = collect_all("sherpa_onnx")
datas += package_datas
binaries += package_binaries
hiddenimports += package_hidden

analysis = Analysis(
    [str(ROOT / "desktop" / "backend_entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "bench",
        "huggingface_hub",
        "psycopg",
        "psycopg_binary",
        "psycopg_pool",
        "pytest",
        "ruff",
        "matplotlib.testing",
        "matplotlib.tests",
        "matplotlib.backends.backend_qt",
        "matplotlib.backends.backend_qt5",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.qt_compat",
        "matplotlib.backends.qt_editor",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="muta-gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gateway",
)
