# -*- mode: python -*-

import os
import platform
import gooey


hookspath = None
if platform.system() == 'Windows':
    hookspath = ['./hooks']

ffmpeg_bin = os.path.join(os.curdir, 'ffmpeg-bin')
if platform.system() == 'Darwin':
    ffmpeg_bin = os.path.join(ffmpeg_bin, 'macos')
elif platform.system() == 'Windows':
    arch_bits = platform.architecture()[0][:2]
    ffmpeg_bin = os.path.join(ffmpeg_bin, 'win{}'.format(arch_bits))
else:
    raise Exception('ffmpeg not available for {}'.format(platform.system()))

gooey_root = os.path.dirname(gooey.__file__)
gooey_languages = Tree(os.path.join(gooey_root, 'languages'), prefix = 'gooey/languages')
gooey_images = Tree(os.path.join(gooey_root, 'images'), prefix = 'gooey/images')
a = Analysis(['./subsync-gui.py'],
             hiddenimports=['pkg_resources.py2_warn'],  # ref: https://github.com/pypa/setuptools/issues/1963
             hookspath=hookspath,
             runtime_hooks=None,
             binaries=[(ffmpeg_bin, 'ffmpeg-bin')],
             )
pyz = PYZ(a.pure)

# runtime options to pass to interpreter -- '-u' is for unbuffered io
options = [('u', None, 'OPTION')]

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          options,
          gooey_languages, # Add them in to collected files
          gooey_images, # Same here.
          name='Subsync',
          debug=False,
          strip=None,
          upx=True,
          console=False,
          windowed=True,
          icon=os.path.join(gooey_root, 'images', 'program_icon.ico'),
          )


if platform.system() == 'Darwin':
    # info_plist = {'addition_prop': 'additional_value'}
    info_plist = {}
    app = BUNDLE(exe,
                 name='Subsync.app',
                 bundle_identifier=None,
                 info_plist=info_plist
                )
