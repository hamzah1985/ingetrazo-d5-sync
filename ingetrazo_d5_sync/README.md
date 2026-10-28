# D5 Sync (experimental)

An optional IngeTrazo extension for syncing geometry, base colors, diffuse
textures, smooth normals and the current camera to D5 Render. It is not loaded
unless the user installs it. This is a prototype for maintainer review, not an
official D5 integration.

## Requirements

Tested on Windows with IngeTrazo 0.5.10, D5 Render 3.1.1.0755, Blender 5.2.2's
Python 3.13 runtime and D5 LiveSync for Blender 1.0.0.0028.

Install these dependencies separately from their publishers:

1. An existing [D5 Render](https://www.d5render.com/download) installation. No D5 installer is included or needed here.
2. [Blender](https://www.blender.org/download/).
3. **D5 LiveSync for Blender**, from the D5 download page. Run its installer
   for the Blender installation that supplies the matching Python runtime.

The plugin needs the add-on's native `d5plugin` module and a Python interpreter
with the same ABI and NumPy installed. It does **not** launch Blender or import
`bpy`. The vendor module stays in its installed location and is not included in
this package. D5's connector API is private and may change between releases.

## Install

1. Close IngeTrazo.
2. Extract the `ingetrazo_d5_sync` folder from the review ZIP into
   `%APPDATA%\ingetrazo\plugins\`. The entry point must be
   `%APPDATA%\ingetrazo\plugins\ingetrazo_d5_sync\__init__.py`.
   Back up an existing folder before replacing it.
3. Start IngeTrazo. The compact toolbar has three SVG buttons: D5 Connect,
   Sync Now and Disconnect. If hidden, use **Extensions > D5 Sync: Show Toolbar**.
4. Save the model as `.igz` and click D5 Connect. Connect opens the native
   Save As popup if the model has not been saved. Cancelling leaves sync off.
5. In D5, open a blank test project or choose New if its connection prompt asks.
   Geometry and camera updates begin when the native connection becomes ready.
   Startup allows three minutes for D5 to launch and the project to become ready;
   the former 45-second limit could stop the worker before project startup finished.

The toolbar adds no text labels or extra full-width row. Tooltips describe its
buttons and connection state. Sync Now also restores the IngeTrazo camera after
independent navigation in D5. Disconnect stops only the plugin's worker and
leaves D5 open. Disable/uninstall the extension while IngeTrazo is closed to
remove it. The model and its companion texture folder are not removed.

Blender's Python is discovered under the normal per-user and Program Files
installation folders, matching its DLL ABI against installed D5 modules.
For a custom runtime, set `INGETRAZO_D5_PYTHON` to its `python.exe` path before
starting IngeTrazo. It must have NumPy and match the installed connector ABI.
The current D5 installation lookup expects `%APPDATA%\D5 Render\`.

For a read-only dependency report, run `runtime.py` using Python:

```powershell
python .\ingetrazo_d5_sync\runtime.py
```

The report checks installed paths and ABI filenames. A successful live
handshake is still required to verify the native module can load and connect.

## How it works

`ingetrazo_d5_sync.py` reads the scene on the GUI thread. It triangulates visible
faces using IngeTrazo's exporter, follows component/group transforms, resolves
face/container paint, and uses the host's UV and smooth-normal calculations.
It sends JSON requests through a separate Python child process to `d5_bridge.py`.
The worker loads the user's installed D5 native module, links to D5 and sends
incremental geometry/material updates and camera poses. Blender stays closed.

The included `.blend` is a generated **empty** source identity for D5's Blender
connection handshake. It contains no user model. Mesh coordinates are converted
from metres to centimetres; positions and normals use matching axes and proper
object rotations. Default unpainted faces use white, non-metallic paint.

Meshes use the connector's `BlenderAddNode` API. Local positions and normals
remain in source axes; the input node matrix swaps its first two columns after
converting translation to centimetres. The native SDK produces the matching
D5 world frame. Its internal V flip is compensated to preserve host texture
mapping. The camera receives an explicitly converted D5 pose. Native export
checks compare actual world positions and normals, including rotated and scaled
components, rather than input arrays alone. Use a new blank D5 project for the
first test after updating, to separate older linked geometry.
Collapsed triangles are skipped while valid geometry continues to sync.

The former `MaxAddIndexTriangles` route produced valid native coordinates and
material values but dark live shading through the Blender connection. On the
same house, camera and lighting, even forced-white materials remained dark;
switching to `BlenderAddNode` displayed white walls and visible pool/grass maps.
The native scene retains CW. An intermediate CCW change based on an incorrect
handedness-only assertion is withdrawn. Readable images and correct coordinates
alone do not establish correct live shading.

The first Connect creates `My model_d5_textures` beside `My model.igz`, even if
there are no textures yet. Readable source images are copied there under content
hash names; originals and old cache images are preserved. Save As or switching
to a different path disconnects sync. Reconnect to create/reuse the companion
folder beside the newly saved file. Runtime diagnostics live under
`%LOCALAPPDATA%\IngeTrazo\d5_sync\`, outside the installed plugin folder.

`ingetrazo-d5-materials.json` in that companion folder records base colors,
roughness, metallic/specular settings, relative image references and the source
asset lookup. It is replaced atomically after capture. Content hashes validate
recovered images when the host's original texture cache disappears. Missing
images fall back to face colors and appear in the material index warnings and
sync status. Nested group paint resolves from the nearest painted container.
Keep this folder beside the saved model when transferring the project.

## Verification and limits

```sh
python -m pytest <extracted-folder>/review_tests
```

These tests need normal IngeTrazo development dependencies, without D5 or Blender.
Native export tests require the matching vendor runtime and installed connector:

```sh
<matching-python> -m unittest discover -s <extracted-folder>/ingetrazo_d5_sync/native_tests -v
```

The local prototype passed 21 installed-engine checks and 11 native-worker
checks before packaging. Live geometry creation, white-paint shading and orbit,
pan, zoom and explicit camera resend were exercised against D5. Smooth normals
survive native export; live curved-surface appearance has not been reviewed.

The coordinate, face-orientation and material-persistence corrections pass all
32 portable checks and 20 native-worker checks. A read-only audit of the local
house exported 4,025 objects, 142 materials and all 11 referenced texture images
without changing its saved document. These checks establish the native export
contract. The live house comparison also verified white walls and visible pool
and grass textures with the Blender submission path under unchanged lighting.
The installed plugin was then started from the IngeTrazo toolbar into a fresh
D5 project: all 246,742 faces loaded, the house rendered normally, and orbiting
in IngeTrazo moved the D5 camera to the matching view.
Live visual acceptance with other recipients' models remains necessary.

Remaining limits include transparency/glass, back-face materials, face-me
figures, edited-group contexts, two-point camera shift, live orthographic visual
acceptance, arbitrary live texture mapping and large-model performance. This
package does not establish full parity with D5's official LiveSync plugins.

## License

Our Python sources, SVG icons and generated empty scene are GPL-3.0-or-later;
see LICENSE. D5 Render and its connector retain their publisher's terms and are
not redistributed. The D5-style SVG is an original text mark used to identify
the connection action; this extension is not affiliated with or endorsed by D5.
