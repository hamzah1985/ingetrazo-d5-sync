# Contributing

Open issues and pull requests here for the IngeTrazo adapter. Keep changes small
and describe the behavior before and after the change. Include relevant tests
and update the setup/limitations documentation when behavior changes.

## Development checks

The adapter uses IngeTrazo's host API. Do not copy its engine into this repository.
The portable tests run against this pinned upstream checkout:

```powershell
git clone https://github.com/ingelibre/ingetrazo.git .test-deps/ingetrazo
git -C .test-deps/ingetrazo checkout a369d1ed1bf3567f98045113b6a64df23b8d5f43
python -m venv .venv
.venv/Scripts/python -m pip install -r .test-deps/ingetrazo/requirements.txt
$env:PYTHONPATH = (Resolve-Path .test-deps/ingetrazo).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONUTF8 = '1'
.venv/Scripts/python -m pytest review_tests -q
```

Use Python 3.13 for the development environment. These 27 portable checks do not
need D5, Blender or a native D5 module. The CI workflow reproduces this setup.

Native offline export checks need the matching Python ABI, NumPy and a separately
installed D5 LiveSync for Blender native module:

```powershell
<matching-python> -m unittest discover -s ingetrazo_d5_sync/native_tests -v
```

Those checks export to temporary files and do not require a running D5 project.
For live changes, use disposable models and report what was visually verified:
geometry updates/deletes, default white shading, camera movement, save/reconnect
and textures. Do not claim unsupported cases are fixed based only on mocks.

## Package changes

`Install.ps1` verifies `CONTENTS.json` before installing. After modifying packaged
files, run `python scripts/update_manifest.py`, then verify without installing:

```powershell
powershell -NoProfile -File Install.ps1 -CheckOnly
```

Review the diff before committing. Do not add D5/Blender installers, native vendor
modules, personal models, texture caches, diagnostics, tokens or account data.
Keep worker code independent of `bpy`; all host scene access must stay on the GUI
thread. Preserve explicit disconnect/timeout cleanup and the companion texture
folder beside each saved model. New contributions use GPL-3.0-or-later.
