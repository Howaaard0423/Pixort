# -*- mode: python ; coding: utf-8 -*-
#
# 把 Pixort 网页版打包成单个 EXE：
#
#     pyinstaller --clean --noconfirm pixort.spec      （或直接双击 build-exe.bat）
#
# 产物：dist/Pixort.exe，双击即启动内置的 HTTP 服务并打开浏览器。
#
# 目录约定（见 backend/pixort_api/settings.py 的 FROZEN 分支）：
#   frontend/      打进 EXE，运行时解包到临时目录，只读
#   assets/        仅桌面客户端与图标使用，不进包
#   illustration_manager.db / illustrations/ / .cache/ 生成在 EXE 同目录，
#   所以备份时把整个文件夹拷走即可。

import os

a = Analysis(
    ['backend/run.py'],
    pathex=['backend'],
    binaries=[],
    datas=[('frontend', 'frontend')],
    hiddenimports=['pixort_api.routes', 'pixort_api.services'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 这些库在打包机上存在，但网页版用不到，排除后体积小很多
    excludes=[
        'PySide6', 'PyQt5', 'PyQt6', 'tkinter',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'pytest', 'pytesseract', 'wordcloud', 'requests',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Pixort',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # 服务端需要一个控制台窗口来显示地址与停止服务
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('assets', 'stack-perspective-fill-18.ico'),
)
