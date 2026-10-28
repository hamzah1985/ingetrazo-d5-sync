# IngeTrazo D5 Sync

Experimental Windows plugin that sends IngeTrazo geometry, colors, diffuse
textures, smooth normals and camera movement to D5 Render. Pull requests and
reproducible bug reports are welcome.

This is an independent, unofficial prototype, tested with IngeTrazo 0.5.10,
D5 Render 3.1.1.0755 and D5 LiveSync for Blender 1.0.0.0028. It is not an
official D5 or IngeTrazo integration.

## Install

1. Have **D5 Render already installed**.
2. Install [Blender](https://www.blender.org/download/) and
   [D5 LiveSync for Blender](https://www.d5render.com/workflow/blender) separately.
   The tested runtime is Blender 5.2.2's Python 3.13 with NumPy. Blender stays
   closed during sync; its matching Python runtime and the installed native
   connector are used by a separate worker.
3. [Download this repository as a ZIP](https://github.com/hamzah1985/ingetrazo-d5-sync/archive/refs/heads/main.zip)
   and extract it. Close IngeTrazo and double-click **Install.cmd**.
   The installer verifies the package manifest, backs up an existing copy and
   installs only our plugin into `%APPDATA%/ingetrazo/plugins/ingetrazo_d5_sync`.
4. Start IngeTrazo. Use **Extensions > D5 Sync: Show Toolbar** if hidden.
   Save a test model and click the compact **D5** connect icon. If D5 asks,
   open a new blank project. Use the arrows button to resend the scene/camera.

The first connection creates `<model-name>_d5_textures` beside the saved `.igz`
file. Save As disconnects sync; reconnect to use the new model location.
Disconnect leaves D5 open. No D5 installer or vendor binaries are included.
This is a source-only package, not an all-dependencies offline bundle.

See [START_HERE.txt](START_HERE.txt) for manual install/uninstall and
[the plugin README](ingetrazo_d5_sync/README.md) for runtime overrides,
architecture, verification and limitations.

## Demo and discussion

The demo video and the original review ZIP are in the
[IngeTrazo suggestion topic](https://github.com/ingelibre/ingetrazo/discussions/1000).

## Contribute

Fork this repository, make a focused change and open a pull request against
`main`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and
test commands. Please include the host/D5/connector versions and reproduction
steps when reporting an issue.

Portable checks cover geometry conversion, normals, camera dispatch, dependency
discovery and controller lifecycle. Native offline checks need the separately
installed D5 connector. Live geometry creation, default white shading, orbit,
pan, zoom and camera resend were exercised during prototype development.

Known gaps include glass/transparency, back-face materials, face-me figures,
edited-group contexts, two-point camera shift, live orthographic appearance,
arbitrary live texture mapping and large-model performance. The private D5
connector API may change. A passing unit suite does not certify live rendering.

## License

Our sources, original SVG icons and generated empty connection scene are
**GPL-3.0-or-later**; see [LICENSE](LICENSE). The `.blend` file contains no user
model and is used only as the connection identity. D5 components retain their
publisher's terms and must be obtained separately. This repository does not
establish permission to redistribute the native connector or a combined binary
bundle. It is not affiliated with or endorsed by D5.
