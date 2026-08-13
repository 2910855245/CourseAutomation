# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['main.py'],
             pathex=['C:\\Users\\win\\Desktop\\逆向工程\\刷课平台js逆向\\Anti-Course Cheating Plugin\\desktop_app'],
             binaries=[],
             datas=[('data', 'data'), ('../HanSansCN_glyfHashedTables.pkl', '.')],
             hiddenimports=['customtkinter', 'scrapling', 'scrapling.parser', 'ddddocr', 'openai', 'httpx', 'requests', 'loguru', 'dotenv', 'darkdetect'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='网课助手',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='网课助手')
