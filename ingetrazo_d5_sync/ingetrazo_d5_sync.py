# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo extension for local geometry, material and camera sync to D5."""
import hashlib
import json
import math
import os
import re
from pathlib import Path
import tempfile

from core.i18n import tr
from .runtime import find_worker_python


ROOT = Path(__file__).resolve().parent
IDENTITY = [[1,0,0,0], [0,1,0,0], [0,0,1,0], [0,0,0,1]]
MATERIAL_CACHE = 'ingetrazo-d5-materials.json'


def read_material_cache(folder):
    path = Path(folder)/MATERIAL_CACHE
    if not path.exists():
        return {'assets': {}}
    if path.resolve().parent != Path(folder).resolve():
        raise ValueError('The D5 material cache points outside the companion folder.')
    record = json.loads(path.read_text(encoding='utf8'))
    if record.get('generator') != 'IngeTrazo D5 Sync' or record.get('format') != 1:
        raise ValueError('The D5 material cache has an unsupported format; it was not overwritten.')
    if not isinstance(record.get('assets'), dict) or not all(
            isinstance(k,str) and isinstance(v,str) for k,v in record['assets'].items()):
        raise ValueError('The D5 material cache has an invalid asset index.')
    return record


def write_material_cache(folder, document_path, materials, assets, warnings):
    folder = Path(folder).resolve()
    portable = []
    for material in sorted(materials, key=lambda item:item['id']):
        item = dict(material)
        if item.get('diffuse_map'):
            image = Path(item['diffuse_map']).resolve()
            if image.parent != folder:
                raise ValueError('Cached material image is outside the companion folder.')
            item['diffuse_map'] = image.name
        portable.append(item)
    record = {'generator':'IngeTrazo D5 Sync', 'format':1,
              'document':Path(document_path).name, 'materials':portable,
              'assets':assets, 'warnings':warnings}
    with tempfile.NamedTemporaryFile(dir=str(folder), suffix='.json.tmp', delete=False) as out:
        temporary = Path(out.name)
        out.write(json.dumps(record, indent=2, ensure_ascii=False).encode('utf8'))
    try:
        os.replace(temporary, folder/MATERIAL_CACHE)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_texture_folder(document_path):
    """Created on first Connect, always beside an already saved IGZ file."""
    if not document_path:
        raise ValueError('Save the IngeTrazo model before starting D5 Sync.')
    document = Path(document_path).resolve()
    if document.suffix.lower() != '.igz' or not document.is_file():
        raise ValueError('Save the model as an IngeTrazo .igz file before starting D5 Sync.')
    folder = document.parent / (document.stem + '_d5_textures')
    folder.mkdir(exist_ok=True)
    if folder.resolve().parent != document.parent:
        raise ValueError('The texture companion folder points outside the model directory.')
    return folder


def cache_texture(source_path, folder, document_path, assets=None):
    """Copy valid images only; content names avoid collisions and overwrites."""
    from core.texture import is_image_file
    source = Path(source_path)
    if not source.is_absolute():
        source = Path(document_path).resolve().parent / source
    source = source.resolve()
    folder = Path(folder).resolve()
    assets = read_material_cache(folder)['assets'] if assets is None else assets
    source_key = os.path.normcase(str(source))
    if not is_image_file(source):
        cached = assets.get(source_key)
        if cached is None:
            matches = {value for key,value in assets.items()
                       if Path(key).name.casefold() == source.name.casefold()}
            cached = next(iter(matches)) if len(matches) == 1 else None
        if cached is not None:
            if not isinstance(cached, str) or not re.fullmatch(r'[0-9a-f]{64}\.[a-z0-9]+', cached):
                raise ValueError('The cached texture index contains an invalid image name.')
            target = (folder/cached).resolve()
            if target.parent != folder:
                raise ValueError('The cached texture points outside the companion folder.')
            if is_image_file(target):
                if hashlib.sha256(target.read_bytes()).hexdigest() != target.stem:
                    raise ValueError('A cached texture does not match its content hash.')
                return target
        raise FileNotFoundError('Texture unavailable: ' + source.name)
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    suffix = source.suffix.lower()
    for signature, extension in [(b'\x89PNG\r\n\x1a\n', '.png'), (b'\xff\xd8\xff', '.jpg'),
                                 (b'GIF', '.gif'), (b'BM', '.bmp'), (b'II*\0', '.tif'),
                                 (b'MM\0*', '.tif'), (b'RIFF', '.webp')]:
        if data.startswith(signature):
            suffix = extension
            break
    target = folder / (digest + suffix)
    assets[source_key] = target.name
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('An existing texture cache file has unexpected contents: ' + str(target))
        return target
    # A completed image becomes visible to D5 in one rename. Originals and
    # unrelated files in the companion folder are never moved or deleted.
    with tempfile.NamedTemporaryFile(dir=str(folder), suffix='.tmp', delete=False) as out:
        temporary = Path(out.name)
        out.write(data)
    try:
        temporary.rename(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def matrix_rows(matrix):
    if matrix is None:
        return [row[:] for row in IDENTITY]
    data = matrix.data()
    return [[float(data[c*4+r]) for c in range(4)] for r in range(4)]


def capture_camera(camera):
    """Use the actual view matrix, including pan, orbit and camera roll."""
    world, invertible = camera.view_matrix().inverted()
    if not invertible:
        raise ValueError('Camera view matrix is not invertible')
    values = world.data()
    vertical_fov = float(camera.fov_deg)
    aspect = float(camera.aspect)
    half_height = float(camera.distance) * math.tan(math.radians(vertical_fov) / 2)
    return {'position': [float(values[i]) for i in (12,13,14)],
            'forward': [-float(values[i]) for i in (8,9,10)],
            'up': [float(values[i]) for i in (4,5,6)],
            'horizontal_fov': math.degrees(2*math.atan(math.tan(math.radians(vertical_fov)/2)*aspect)),
            'orthographic': not bool(camera.perspective),
            'orthographic_width': 2*half_height*aspect}


def capture_scene(scene, document_path=None, texture_folder=None):
    """Read scene on its GUI thread; images copy only into its companion folder."""
    from formats.meshexport import export_triangles, SmoothNormals
    from core.materials import effective_attrs
    from core.texture import affine_uv, planar_uv
    materials = {}
    objects = []
    cached = {}
    warnings = []
    assets = read_material_cache(texture_folder)['assets'] if texture_folder is not None else {}
    smoother = SmoothNormals()

    def mesh_parts(mesh, path, name, matrix, paint, loose=False):
        parts = {}
        for face in mesh.faces:
            if not scene.entity_visible(face):
                continue
            attrs = effective_attrs(face.attrs, paint) or {}
            color = attrs.get('color') or (1.0, 1.0, 1.0)
            color = '#' + ''.join('%02X' % max(0, min(255, round(float(c)*255))) for c in color[:3])
            texture = attrs.get('texture') or {}
            texture_path = texture.get('path')
            diffuse_map = None
            if texture_path:
                if not document_path or texture_folder is None:
                    raise ValueError('Save the model and connect D5 Sync before sending textures.')
                if texture_path not in cached:
                    try:
                        cached[texture_path] = cache_texture(texture_path, texture_folder, document_path, assets)
                    except FileNotFoundError as error:
                        cached[texture_path] = None
                        warnings.append(str(error) + '; using the face color.')
                if cached[texture_path] is not None:
                    diffuse_map = str(cached[texture_path])
                    # The host's own mesh exporter uses white for textured faces.
                    color = '#FFFFFF'
            mat_name = attrs.get('mat') or ('Default White' if not attrs.get('color') and not diffuse_map
                                            else 'Color ' + color)
            identity = json.dumps([mat_name, color, Path(diffuse_map).name if diffuse_map else ''], sort_keys=True)
            mid = hashlib.sha256(identity.encode('utf8')).hexdigest()[:24]
            materials[mid] = {'id': mid, 'name': mat_name, 'color': color,
                              'metallic': 0.0, 'specular': 0.5, 'roughness': 0.5}
            if diffuse_map:
                materials[mid]['diffuse_map'] = diffuse_map
            part = parts.setdefault(mid, {'id': path + '/' + mid, 'name': name,
                                          'vertices': [], 'triangles': [],
                                          'uvs': [], 'normals': [],
                                          'material_id': mid, 'transform': matrix_rows(matrix)})
            smooth = smoother.corners(face)
            flat = smoother.flat(face)
            for tri in export_triangles(face):
                start = len(part['vertices'])
                part['vertices'].extend([[float(p.x()), float(p.y()), float(p.z())] for p in tri])
                part['normals'].extend([list(smooth.get(p.toTuple(), flat).toTuple()) for p in tri])
                if diffuse_map:
                    uvw = texture.get('uvw')
                    uv = affine_uv(uvw, tri) if uvw else planar_uv(
                        face.normal(), tri, texture.get('sw', 1.0) or 1.0,
                        texture.get('sh', 1.0) or 1.0, float(texture.get('rot', 0.0)))
                    part['uvs'].extend([[float(u), float(v)] for u, v in uv])
                else:
                    part['uvs'].extend([[0.0, 0.0] for _ in tri])
                part['triangles'].append([start, start+1, start+2])
        objects.extend(part for part in parts.values() if part['triangles'])

    def group_parts(group, parent, path, top_paint):
        if not scene.entity_visible(group):
            return
        local = getattr(group, 'xform', None)
        world = local if parent is None else parent if local is None else parent * local
        path = path + '/' + str(group.uid)
        paint = getattr(group, 'material', None) or top_paint
        mesh_parts(group.mesh, path, getattr(group, 'name', '') or 'Group', world, paint)
        for child in getattr(group, 'children', ()) or ():
            group_parts(child, world, path, paint)

    mesh_parts(scene.loose_mesh, 'loose', 'Loose geometry', None, None, loose=True)
    for group in scene.groups:
        group_parts(group, None, 'group', getattr(group, 'material', None))
    snapshot = {'materials': list(materials.values()), 'objects': objects}
    if texture_folder is not None:
        snapshot['texture_folder'] = str(Path(texture_folder).resolve())
        snapshot['document_path'] = str(Path(document_path).resolve())
        write_material_cache(texture_folder, document_path, snapshot['materials'], assets, warnings)
    if warnings:
        snapshot['warnings'] = warnings
    return snapshot


class SyncController:
    def __init__(self, app):
        from PySide6.QtCore import QProcess, QTimer
        self.app = app
        self.process = QProcess(app.window)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self.read_replies)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.errorOccurred.connect(self.process_error)
        self.process.finished.connect(self.finished)
        self.process.started.connect(self.request_info)
        self.timer = QTimer(app.window)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.capture)
        self.startup = QTimer(app.window)
        self.startup.setSingleShot(True)
        self.startup.setInterval(180000)
        self.startup.timeout.connect(self.startup_timeout)
        self.buffer = ''
        self.busy = False
        self.ready = False
        self.enabled = False
        self.pending = None
        self.acknowledged = None
        self.install_camera_tracking()
        app.on_document_changed(self.schedule)
        self._create_toolbar()

    def _create_toolbar(self):
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QAction, QIcon
        from PySide6.QtWidgets import QToolBar
        window = self.app.window
        self.toolbar = QToolBar('IngeTrazo → D5 Sync', window)
        self.toolbar.setObjectName('ingetrazo_d5_sync_toolbar')
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.connect_action = QAction(QIcon(str(ROOT/'icons'/'logo.svg')), tr('Connect'), window)
        self.connect_action.setToolTip(tr('Connect IngeTrazo to D5 Render'))
        self.connect_action.triggered.connect(lambda _checked=False: self.connect())
        self.sync_action = QAction(QIcon(str(ROOT/'icons'/'sync.svg')), tr('Sync Now'), window)
        self.sync_action.setToolTip(tr('Send the current model to D5 Render'))
        self.sync_action.triggered.connect(lambda _checked=False: self.sync_now())
        self.disconnect_action = QAction(QIcon(str(ROOT/'icons'/'disconnect.svg')), tr('Disconnect'), window)
        self.disconnect_action.setToolTip(tr('Stop sending updates and keep D5 open'))
        self.disconnect_action.triggered.connect(lambda _checked=False: self.stop())
        for action in (self.connect_action, self.sync_action, self.disconnect_action):
            self.toolbar.addAction(action)
        window.addToolBar(Qt.TopToolBarArea, self.toolbar)
        self.app.add_menu_action(tr('D5 Sync: Show Toolbar'), self.show_toolbar)
        self.app.add_menu_action(tr('D5 Sync: Connect / Disconnect'), self.toggle)
        self._update_actions()
        self.toolbar.show()

    def show_toolbar(self):
        self.toolbar.show()
        self.toolbar.raise_()

    def _update_actions(self):
        if not hasattr(self, 'connect_action'):
            return
        self.connect_action.setEnabled(not self.enabled and not getattr(self, '_stopping', False))
        self.sync_action.setEnabled(self.enabled and self.ready)
        self.disconnect_action.setEnabled(self.enabled)
        state = ('Disconnecting' if getattr(self, '_stopping', False) else
                 'Connected' if self.ready and self.enabled else
                 'Connecting' if self.enabled else 'Disconnected')
        self.connect_action.setToolTip(tr('D5 Sync: {state}', state=tr(state)))

    def connect(self):
        if not self.enabled:
            self.toggle()

    def install_camera_tracking(self):
        from PySide6.QtCore import QTimer
        if not hasattr(self, 'reply_timeout'):
            self.reply_timeout = QTimer(self.app.window)
            self.reply_timeout.setSingleShot(True)
            self.reply_timeout.setInterval(60000)
            self.reply_timeout.timeout.connect(self.response_timeout)
            self.document_location = getattr(self, 'document_path', None)
        if not hasattr(self, 'stop_timeout'):
            self.stop_timeout = QTimer(self.app.window)
            self.stop_timeout.setSingleShot(True)
            self.stop_timeout.setInterval(1500)
            self.stop_timeout.timeout.connect(self.kill_stalled_worker)
            self._stopping = False
            self._restart_after_stop = False
        if hasattr(self, 'camera_timer'):
            return
        self.camera_timer = QTimer(self.app.window)
        self.camera_timer.setInterval(33)
        self.camera_timer.timeout.connect(self.poll_camera)
        self.camera_inflight = False
        self.camera_capable = False
        self.camera_acknowledged = None
        self.camera_sends = 0
        self.camera_acks = 0

    def poll_camera(self):
        if not self.enabled or not self.ready or not self.document_matches():
            return
        if not self.camera_capable or self.busy or self.camera_inflight:
            return
        try:
            camera = capture_camera(self.app.viewport.camera)
            key = json.dumps(camera, sort_keys=True)
            if key == self.camera_acknowledged:
                return
            self.camera_inflight = True
            self.camera_sent_key = key
            self.write_request((json.dumps({'op':'camera', 'camera':camera})+'\n').encode('utf8'))
            self.camera_sends += 1
        except Exception as error:
            self.camera_inflight = False
            self.status('D5 camera sync failed: ' + str(error))

    def sync_now(self):
        if self.enabled and self.ready:
            self.acknowledged = None
            self.camera_acknowledged = None
            self.capture()

    def status(self, text):
        print('[IngeTrazo D5 prototype] ' + text)
        self.app.window.statusBar().showMessage(tr(text), 15000)

    def document_matches(self):
        """Observe Save As/New/Open even when there is no geometry edit."""
        current = getattr(self.app.window, '_current_path', None)
        if current and current == self.document_location:
            return True
        if current and Path(current).resolve() == self.document_path:
            self.document_location = current
            return True
        self.stop()
        self.status('Model location changed. Reconnect D5 Sync to use its new texture folder.')
        return False

    def write_request(self, payload):
        written = self.process.write(payload)
        if written is not None and written < 0:
            self.stop()
            raise RuntimeError('D5 Sync could not send an update. Reconnect using the D5 icon.')
        if not self.reply_timeout.isActive():
            self.reply_timeout.start()

    def response_timeout(self):
        if self.enabled:
            self.stop()
            self.status('D5 is not responding. Reconnect using the D5 icon when it is ready.')

    def process_error(self, error):
        from PySide6.QtCore import QProcess
        if getattr(self, '_stopping', False):
            # A timed-out worker can emit Crashed when our own kill completes.
            # Keep an intentional reconnect queued until finished arrives.
            return
        self._restart_after_stop = False
        detail = self.process.errorString()
        if error == QProcess.ProcessError.FailedToStart:
            # FailedToStart does not emit finished; release the toolbar now.
            self.finished()
        else:
            self.stop()
        self.status('D5 Sync stopped: ' + detail)

    def toggle(self):
        if getattr(self, '_stopping', False):
            return
        if self.enabled:
            self.stop()
            return
        try:
            saved_path = getattr(self.app.window, '_current_path', None)
            valid_saved_path = (saved_path and Path(saved_path).suffix.lower() == '.igz'
                                and Path(saved_path).is_file())
            if not valid_saved_path:
                save_as = getattr(self.app.window, '_on_save_as', None)
                if callable(save_as):
                    save_as()
                    saved_path = getattr(self.app.window, '_current_path', None)
                    if not saved_path or Path(saved_path).suffix.lower() != '.igz' or not Path(saved_path).is_file():
                        self.status('Save cancelled or unsuccessful. D5 Sync remains disconnected.')
                        return
            self.document_path = Path(saved_path).resolve() if saved_path else None
            self.texture_folder = prepare_texture_folder(self.document_path)
            self.document_location = saved_path
        except (OSError, ValueError) as error:
            self.status(str(error))
            return
        try:
            python = find_worker_python()
        except (OSError, ValueError) as error:
            self.status(str(error))
            return
        worker = ROOT / 'd5_bridge.py'
        if not python.exists() or not worker.exists():
            self.status('D5 prototype runtime or worker is missing.')
            return
        runtime_data = Path(os.environ['LOCALAPPDATA']) / 'IngeTrazo' / 'd5_sync'
        try:
            runtime_data.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.status('D5 Sync could not create its diagnostics folder: ' + str(error))
            return
        self.enabled = True
        self.ready = False
        self.acknowledged = None
        self.buffer = ''
        self.process.setProgram(str(python))
        self.process.setArguments(['-u', str(worker), '--stdio', '--launch', '--connect',
                                   '--source', str(ROOT / 'ingetrazo-d5-probe.blend'),
                                   '--output', str(runtime_data / 'worker-result.json')])
        self.process.start()
        self.startup.start()
        self._update_actions()
        # stdin queues while the native startup runs. A valid info reply marks
        # the handshake ready; the worker itself does not emit an unsolicited one.
        self.status('Connecting to D5 Render…')

    def request_info(self):
        try:
            self.write_request(b'{"op":"info"}\n')
        except RuntimeError as error:
            self.status(str(error))

    def schedule(self):
        if self.enabled and self.document_matches():
            self.timer.start()

    def capture(self):
        if not self.enabled or not self.ready:
            return
        try:
            if not self.document_matches():
                return
            self.pending = capture_scene(self.app.scene, self.document_path, self.texture_folder)
            self.send_pending()
        except Exception as error:
            self.status('D5 capture failed: ' + str(error))

    def send_pending(self):
        if not self.enabled or not self.ready or self.busy or self.pending is None:
            return
        serialized = json.dumps(self.pending, sort_keys=True, separators=(',', ':'))
        self.inflight_warnings = self.pending.get('warnings', [])
        self.pending = None
        if serialized == self.acknowledged:
            return
        self.inflight = serialized
        self.busy = True
        self.write_request(('{"op":"snapshot","scene":' + serialized + '}\n').encode('utf8'))

    def read_replies(self):
        incoming = bytes(self.process.readAllStandardOutput()).decode('utf8', errors='replace')
        if not self.enabled or getattr(self, '_stopping', False):
            self.buffer = ''
            return
        self.buffer += incoming
        while '\n' in self.buffer:
            if not self.enabled or getattr(self, '_stopping', False):
                self.buffer = ''
                return
            line, self.buffer = self.buffer.split('\n', 1)
            if not line.strip():
                continue
            try:
                result = json.loads(line)
                if not isinstance(result, dict):
                    raise ValueError('Expected a reply object')
            except ValueError:
                self.status('D5 worker protocol error.')
                self.stop()
                return
            if not result.get('ok'):
                self.status('D5 connection failed: ' + result.get('error', 'unknown error'))
                self.stop()
                return
            if result.get('op') == 'info':
                self.startup.stop()
                self.ready = True
                self.camera_capable = bool(result.get('camera_sync'))
                self.camera_acknowledged = None
                if self.camera_capable:
                    self.camera_timer.start()
                self._update_actions()
                self.capture()
            elif result.get('op') == 'snapshot':
                self.acknowledged = self.inflight
                self.busy = False
                warnings = getattr(self, 'inflight_warnings', [])
                self.status('Model synced to D5 Render.' if not warnings else
                            'Model synced; %d texture(s) unavailable. See the companion material cache.' % len(warnings))
                self.send_pending()
            elif result.get('op') == 'camera':
                self.camera_inflight = False
                self.camera_acknowledged = self.camera_sent_key
                self.camera_acks += 1
            if self.enabled and (self.busy or self.camera_inflight):
                self.reply_timeout.start()
            else:
                self.reply_timeout.stop()

    def read_errors(self):
        text = bytes(self.process.readAllStandardError()).decode('utf8', errors='replace')
        if text:
            print('[D5 worker] ' + text.rstrip())

    def startup_timeout(self):
        self.status('D5 did not become ready within 45 seconds.')
        self.stop()

    def stop(self):
        from PySide6.QtCore import QProcess
        self.enabled = False
        self.ready = False
        self.busy = False
        self.pending = None
        self.timer.stop()
        self.startup.stop()
        if hasattr(self, 'reply_timeout'):
            self.reply_timeout.stop()
        if hasattr(self, 'camera_timer'):
            self.camera_timer.stop()
            self.camera_inflight = False
        self._stopping = self.process.state() != QProcess.ProcessState.NotRunning
        self._stopping_pid = self.process.processId()
        self._update_actions()
        if self._stopping:
            self.process.write(b'{"op":"quit"}\n')
            self.process.closeWriteChannel()
            self.stop_timeout.start()
        elif getattr(self, '_restart_after_stop', False):
            self.finished()

    def reconnect_worker(self):
        self._restart_after_stop = True
        self.stop()

    def kill_stalled_worker(self):
        from PySide6.QtCore import QProcess
        if (getattr(self, '_stopping', False) and self.process.processId() == self._stopping_pid
                and self.process.state() != QProcess.ProcessState.NotRunning):
            self.process.kill()

    def finished(self, *args):
        self._stopping = False
        if hasattr(self, 'stop_timeout'):
            self.stop_timeout.stop()
        self.enabled = False
        self.ready = False
        self.busy = False
        self.timer.stop()
        self.startup.stop()
        if hasattr(self, 'reply_timeout'):
            self.reply_timeout.stop()
        if hasattr(self, 'camera_timer'):
            self.camera_timer.stop()
            self.camera_inflight = False
        self._update_actions()
        if getattr(self, '_restart_after_stop', False):
            self._restart_after_stop = False
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.connect)


def setup(app):
    existing = getattr(app.window, '_d5_sync_prototype', None)
    if existing is not None:
        existing.show_toolbar()
        return
    controller = SyncController(app)
    app.window.__dict__['_d5_sync_prototype'] = controller
