# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Icosele Vault

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('data', 'data'),
        ('config', 'config'),
        ('plugins', 'plugins'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'app.platform_utils',
        'app.audit_log',
        'app.snapshot_store',
        'app.webhook_manager',
        'app.plugin_manager',
        'app.ollama_client',
        'app.host_monitor',
        'app.web_console',
        'app.auth_manager',
        'app.replication_manager',
        'app.compliance_reports',
        'app.usb_monitor',
        'app.qemu.process',
        'app.qemu.qmp',
        'app.ui.vm_controls',
        'app.ui.vm_list',
        'app.ui.vm_create_dialog',
        'app.ui.theme',
        'app.ui.snapshot_dag_panel',
        'app.ui.snapshot_panel',
        'app.ui.ai_assistant_panel',
        'app.ui.dashboard_panel',
        'app.ui.cloud_panel',
        'app.ui.enterprise_panel',
        'config.vm_config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='IcoseleVault',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.png',
)
