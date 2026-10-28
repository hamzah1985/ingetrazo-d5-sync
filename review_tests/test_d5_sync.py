# SPDX-License-Identifier: GPL-3.0-or-later
"""D5 example tests: no Blender, D5, installed app or network required."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QMatrix4x4, QVector3D, QImage, QColor
from core.scene import Scene
from core.mesh import Mesh
from core.group import Group
from core.extensions import _import_by_path
from core.i18n import set_language

ROOT = Path(__file__).resolve().parents[1] / 'ingetrazo_d5_sync'
_package = _import_by_path('d5_sync_test', ROOT/'__init__.py')
adapter = sys.modules[_package.SyncController.__module__]
capture_scene = adapter.capture_scene
matrix_rows = adapter.matrix_rows
prepare_texture_folder = adapter.prepare_texture_folder
SyncController = adapter.SyncController
capture_camera = adapter.capture_camera

def triangle(mesh, color=None):
    face = mesh.add_face([QVector3D(0,0,0), QVector3D(1.25,0,0), QVector3D(0,1.25,0)])
    if color:
        face.attrs['color'] = color
    return face

class TestD5SyncAdapter(unittest.TestCase):
    def test_nested_container_paint_uses_nearest_parent(self):
        scene = Scene()
        parent = Group(name='Parent')
        child = Group(name='Child')
        leaf = Group(name='Leaf')
        parent.material = {'color':(1,0,0)}
        child.material = {'color':(0,0,1)}
        triangle(leaf.mesh)
        parent.children.append(child)
        child.children.append(leaf)
        scene.groups.append(parent)
        self.assertEqual([m['color'] for m in capture_scene(scene)['materials']], ['#0000FF'])

    def test_material_manifest_and_cached_image_survive_missing_original(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root/'Kitchen.igz'
            project.write_text('test document')
            image = QImage(2,2,QImage.Format_RGB32)
            image.fill(QColor('white'))
            source = root/'original.png'
            self.assertTrue(image.save(str(source)))
            scene = Scene()
            face = triangle(scene.loose_mesh)
            face.attrs['texture'] = {'path':str(source),'sw':1,'sh':1}
            folder = prepare_texture_folder(project)
            first = capture_scene(scene, project, folder)
            manifest = json.loads((folder/adapter.MATERIAL_CACHE).read_text(encoding='utf8'))
            self.assertEqual(manifest['materials'][0]['diffuse_map'], Path(first['materials'][0]['diffuse_map']).name)
            self.assertEqual(manifest['materials'][0]['color'], '#FFFFFF')
            source.unlink()
            reopened = capture_scene(scene, project, folder)
            self.assertEqual(first, reopened)
            self.assertTrue(Path(reopened['materials'][0]['diffuse_map']).is_file())

    def test_same_image_from_a_new_host_cache_keeps_material_identity(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root/'Kitchen.igz'
            project.touch()
            image = QImage(2,2,QImage.Format_RGB32)
            image.fill(QColor('red'))
            a,b = root/'cache-a.png',root/'cache-b.png'
            self.assertTrue(image.save(str(a)))
            b.write_bytes(a.read_bytes())
            scene = Scene()
            face = triangle(scene.loose_mesh)
            face.attrs['texture'] = {'path':str(a),'sw':1,'sh':1}
            folder = prepare_texture_folder(project)
            first = capture_scene(scene,project,folder)
            face.attrs['texture']['path'] = str(b)
            second = capture_scene(scene,project,folder)
            self.assertEqual(first['materials'],second['materials'])

    def test_missing_image_keeps_scene_and_reports_color_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)/'Kitchen.igz'
            project.touch()
            scene = Scene()
            face = triangle(scene.loose_mesh, (0.8,0.6,0.4))
            face.attrs['texture'] = {'path':str(Path(temp)/'missing.png')}
            snapshot = capture_scene(scene,project,prepare_texture_folder(project))
            self.assertEqual(snapshot['materials'][0]['color'],'#CC9966')
            self.assertNotIn('diffuse_map',snapshot['materials'][0])
            self.assertEqual(len(snapshot['objects']),1)
            self.assertEqual(len(snapshot['warnings']),1)

    def test_cached_image_index_cannot_escape_companion_folder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root/'companion'
            folder.mkdir()
            missing = root/'missing.png'
            assets = {os.path.normcase(str(missing.resolve())):'../outside.png'}
            with self.assertRaisesRegex(ValueError,'invalid image name'):
                adapter.cache_texture(missing,folder,root/'Kitchen.igz',assets)

    def setUp(self):
        set_language('en')
        runtime = patch.object(adapter, 'find_worker_python', return_value=Path(sys.executable))
        runtime.start()
        self.addCleanup(runtime.stop)

    def test_soft_edges_keep_smooth_normals_and_hard_edges_keep_creases(self):
        import math
        scene = Scene()
        mesh = scene.loose_mesh
        mesh.add_face([QVector3D(0,0,0), QVector3D(1,0,0), QVector3D(0,1,0)])
        mesh.add_face([QVector3D(1,0,0), QVector3D(0,0,0), QVector3D(0,0,1)])
        seam = next(e for e in mesh.edges if len(e.faces) == 2)
        hard = capture_scene(scene)['objects'][0]
        self.assertEqual({tuple(n) for p,n in zip(hard['vertices'],hard['normals']) if p == [0,0,0]},
                         {(0,0,1),(0,1,0)})
        seam.soft = True
        before = scene.version
        smooth = capture_scene(scene)['objects'][0]
        for p,n in zip(smooth['vertices'],smooth['normals']):
            if p in ([0,0,0],[1,0,0]):
                self.assertAlmostEqual(n[0],0)
                self.assertAlmostEqual(n[1],1/math.sqrt(2),places=5)
                self.assertAlmostEqual(n[2],1/math.sqrt(2),places=5)
        self.assertEqual(len(smooth['normals']),len(smooth['vertices']))
        self.assertEqual(scene.version,before)
        seam.soft = False
        self.assertEqual(capture_scene(scene)['objects'][0]['normals'],hard['normals'])


    def test_sync_now_restores_camera_after_independent_d5_movement(self):
        controller = SyncController.__new__(SyncController)
        controller.enabled = controller.ready = True
        controller.acknowledged = 'previous model'
        controller.camera_acknowledged = 'previous camera'
        captures = []
        controller.capture = lambda:captures.append(True)
        controller.sync_now()
        self.assertIsNone(controller.acknowledged)
        self.assertIsNone(controller.camera_acknowledged)
        self.assertEqual(captures,[True])


    def test_default_faces_are_white_and_explicit_paint_is_preserved(self):
        scene = Scene()
        triangle(scene.loose_mesh)
        snapshot = capture_scene(scene)
        self.assertEqual(snapshot['materials'][0]['color'], '#FFFFFF')
        self.assertEqual(snapshot['materials'][0]['name'], 'Default White')
        scene.loose_mesh.faces[0].attrs['color'] = (.96, .95, .925)
        painted = capture_scene(scene)
        self.assertEqual(painted['materials'][0]['color'], '#F5F2EC')
        self.assertNotEqual(snapshot['materials'][0]['id'], painted['materials'][0]['id'])


    def test_hidden_faces_inside_groups_are_not_exported(self):
        scene = Scene()
        group = Group(name='Partly hidden')
        face = triangle(group.mesh)
        scene.groups.append(group)
        self.assertEqual(len(capture_scene(scene)['objects']), 1)
        face.attrs['hidden'] = True
        self.assertEqual(capture_scene(scene)['objects'], [])


    def test_late_reply_cannot_restart_disconnected_sync(self):
        from types import SimpleNamespace
        controller = SyncController.__new__(SyncController)
        controller.enabled = controller.ready = False
        controller._stopping = True
        controller.buffer = 'old partial reply'
        controller.process = SimpleNamespace(readAllStandardOutput=lambda:b'{"ok":true,"op":"info","camera_sync":true}\n')
        controller.read_replies()
        self.assertFalse(controller.ready)
        self.assertEqual(controller.buffer, '')


    def test_failed_launch_releases_state_without_finished_signal(self):
        from types import SimpleNamespace
        from PySide6.QtCore import QProcess
        controller = SyncController.__new__(SyncController)
        timer = SimpleNamespace(stop=lambda:None)
        controller.timer = controller.startup = controller.reply_timeout = timer
        controller.enabled = True
        controller.ready = False
        controller._restart_after_stop = True
        controller.process = SimpleNamespace(errorString=lambda:'Executable unavailable')
        messages = []
        controller.status = messages.append
        controller.process_error(QProcess.ProcessError.FailedToStart)
        self.assertFalse(controller.enabled)
        self.assertFalse(controller.ready)
        self.assertFalse(controller._restart_after_stop)
        self.assertIn('Executable unavailable', messages[-1])


    def test_expected_worker_kill_does_not_cancel_reconnect(self):
        from PySide6.QtCore import QProcess
        controller = SyncController.__new__(SyncController)
        controller._stopping = controller._restart_after_stop = True
        controller.process_error(QProcess.ProcessError.Crashed)
        self.assertTrue(controller._restart_after_stop)


    def test_save_as_stops_camera_before_another_geometry_edit(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as temp:
            project = Path(temp)/'Original.igz'
            renamed = Path(temp)/'Renamed.igz'
            project.write_bytes(b'saved')
            renamed.write_bytes(b'saved')
            controller = SyncController.__new__(SyncController)
            controller.app = SimpleNamespace(window=SimpleNamespace(_current_path=renamed))
            controller.document_path = project.resolve()
            controller.document_location = project
            controller.enabled = controller.ready = True
            messages, stopped = [], []
            controller.stop = lambda:stopped.append(True)
            controller.status = messages.append
            controller.poll_camera()
            self.assertEqual(stopped, [True])
            self.assertIn('location changed', messages[-1])
            self.assertFalse((Path(temp)/'Original_d5_textures').exists())


    def test_unresponsive_worker_and_failed_write_disconnect_cleanly(self):
        from types import SimpleNamespace
        controller = SyncController.__new__(SyncController)
        controller.enabled = True
        stopped, messages = [], []
        controller.stop = lambda:stopped.append(True)
        controller.status = messages.append
        controller.response_timeout()
        self.assertEqual(stopped, [True])
        self.assertIn('not responding', messages[-1])
        controller.process = SimpleNamespace(write=lambda packet:-1)
        with self.assertRaisesRegex(RuntimeError, 'could not send'):
            controller.write_request(b'{"op":"info"}\n')
        self.assertEqual(stopped, [True, True])


    def test_worker_restart_waits_for_old_worker_and_never_targets_d5(self):
        from types import SimpleNamespace
        from PySide6.QtCore import QProcess, QTimer
        events = []
        process = SimpleNamespace(state=lambda:QProcess.ProcessState.Running, processId=lambda:123,
                                  write=lambda data:events.append('quit'),
                                  closeWriteChannel=lambda:events.append('close stdin'),
                                  kill=lambda:events.append('kill owned worker'))
        timer = SimpleNamespace(stop=lambda:None, start=lambda:None)
        controller = SyncController.__new__(SyncController)
        controller.process = process
        controller.timer = controller.startup = controller.stop_timeout = timer
        controller.enabled = controller.ready = True
        controller.connect = lambda:events.append('restart')
        controller.reconnect_worker()
        self.assertEqual(events, ['quit','close stdin'])
        self.assertFalse(controller.enabled)
        controller.kill_stalled_worker()
        self.assertEqual(events[-1], 'kill owned worker')
        original_single_shot = QTimer.singleShot
        try:
            QTimer.singleShot = lambda delay,fn:fn()
            controller.finished()
        finally:
            QTimer.singleShot = original_single_shot
        self.assertEqual(events[-1], 'restart')


    def test_camera_capture_fov_and_latest_pose_only(self):
        import math
        from types import SimpleNamespace
        from core.camera import OrbitCamera
        camera = OrbitCamera()
        camera.aspect = 2
        first = capture_camera(camera)
        expected_fov = math.degrees(2*math.atan(math.tan(math.radians(45)/2)*2))
        self.assertAlmostEqual(first['horizontal_fov'], expected_fov)
        self.assertAlmostEqual(sum(v*v for v in first['forward']),1,places=5)
        self.assertAlmostEqual(sum(a*b for a,b in zip(first['forward'], first['up'])),0,places=5)
        controller = SyncController.__new__(SyncController)
        controller.app = SimpleNamespace(viewport=SimpleNamespace(camera=camera),
                                         window=SimpleNamespace(_current_path=ROOT/'camera.igz'))
        controller.document_location = controller.document_path = ROOT/'camera.igz'
        controller.reply_timeout = SimpleNamespace(isActive=lambda:False, start=lambda:None)
        packets = []
        controller.process = SimpleNamespace(write=packets.append)
        controller.enabled = controller.ready = controller.camera_capable = True
        controller.busy = controller.camera_inflight = False
        controller.camera_acknowledged = None
        controller.camera_sends = 0
        controller.poll_camera()
        controller.poll_camera()
        self.assertEqual(len(packets),1)
        controller.camera_inflight = False
        controller.camera_acknowledged = controller.camera_sent_key
        controller.poll_camera()
        self.assertEqual(len(packets),1)
        camera.yaw += .25
        controller.poll_camera()
        self.assertEqual(len(packets),2)
        self.assertEqual(json.loads(packets[1])['op'],'camera')
        camera.perspective = False
        self.assertTrue(capture_camera(camera)['orthographic'])


    def test_toolbar_svg_actions_and_duplicate_setup(self):
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
        from views.extension_api import ExtensionApp
        setup = _package.setup
        application = QApplication.instance() or QApplication([])
        class Viewport(QObject):
            sceneVersionChanged = Signal(int)
        window = QMainWindow()
        window.viewport = Viewport(window)
        window.viewport.scene = Scene()
        window._current_path = None
        save_calls = []
        window._on_save_as = lambda: save_calls.append('popup')
        window._ext_menu = window.menuBar().addMenu('Extensions')
        window._ext_anchor = None
        app = ExtensionApp(window, 'ingetrazo_d5_sync')
        setup(app)
        controller = window._d5_sync_prototype
        toolbar = controller.toolbar
        self.assertEqual(toolbar.objectName(), 'ingetrazo_d5_sync_toolbar')
        from PySide6.QtCore import QSize, Qt
        self.assertEqual(toolbar.iconSize(), QSize(20, 20))
        self.assertEqual(toolbar.toolButtonStyle(), Qt.ToolButtonIconOnly)
        self.assertEqual([a.text() for a in toolbar.actions()], ['Connect', 'Sync Now', 'Disconnect'])
        self.assertTrue(controller.connect_action.isEnabled())
        self.assertFalse(controller.sync_action.isEnabled())
        self.assertFalse(controller.disconnect_action.isEnabled())
        for action in toolbar.actions():
            pixmap = action.icon().pixmap(28, 28)
            self.assertFalse(pixmap.isNull(), action.text())
            image = pixmap.toImage()
            self.assertTrue(any(image.pixelColor(x,y).alpha() for x in range(image.width())
                                for y in range(image.height())), action.text())
        controller.connect_action.trigger()
        self.assertEqual(save_calls, ['popup'])
        self.assertFalse(controller.enabled)
        self.assertIn('Save', window.statusBar().currentMessage())
        setup(app)
        self.assertEqual(len(window.findChildren(QToolBar)), 1)
        self.assertTrue(any('D5 Sync' in a.text() for a in window.createPopupMenu().actions()))
        controller.toolbar.hide()
        controller.show_toolbar()
        self.assertFalse(controller.toolbar.isHidden())
        window.close()
        window.deleteLater()
        application.processEvents()


    def test_first_connect_creates_companion_folder_and_reuses_it(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as temp:
            project = Path(temp) / 'My kitchen.igz'
            project.write_bytes(b'test-only saved document marker')
            expected = project.parent / 'My kitchen_d5_textures'
            starts = []
            class FakeProcess:
                def setProgram(self, value): pass
                def setArguments(self, value): pass
                def start(self): starts.append(expected.is_dir())
            controller = SyncController.__new__(SyncController)
            controller.app = SimpleNamespace(window=SimpleNamespace(_current_path=project))
            controller.process = FakeProcess()
            controller.startup = SimpleNamespace(start=lambda: None)
            controller.status = lambda text: None
            controller.enabled = False
            self.assertFalse(expected.exists())
            controller.toggle()
            self.assertEqual(starts, [True])
            keep = expected / 'user-note.txt'
            keep.write_text('preserve me')
            controller.enabled = False
            controller.toggle()
            self.assertEqual(starts, [True, True])
            self.assertEqual(keep.read_text(), 'preserve me')
            self.assertEqual(project.read_bytes(), b'test-only saved document marker')


    def test_unsaved_model_does_not_start_worker_or_choose_another_cache(self):
        from types import SimpleNamespace
        controller = SyncController.__new__(SyncController)
        save_calls = []
        controller.app = SimpleNamespace(window=SimpleNamespace(
            _current_path=None, _on_save_as=lambda: save_calls.append('popup')))
        controller.enabled = False
        messages = []
        controller.status = messages.append
        controller.toggle()
        self.assertEqual(save_calls, ['popup'])
        self.assertFalse(controller.enabled)
        self.assertIn('Save', messages[-1])


    def test_save_popup_success_continues_connection_and_creates_folder(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as temp:
            project = Path(temp)/'Saved from popup.igz'
            window = SimpleNamespace(_current_path=None)
            calls = []
            def save_as():
                calls.append('save popup')
                project.write_bytes(b'test-only save result')
                window._current_path = project
            window._on_save_as = save_as
            class Process:
                def setProgram(self, value): pass
                def setArguments(self, value): pass
                def start(self): calls.append('worker start')
            controller = SyncController.__new__(SyncController)
            controller.app = SimpleNamespace(window=window)
            controller.process = Process()
            controller.startup = SimpleNamespace(start=lambda: None)
            controller.status = lambda message: None
            controller.enabled = False
            controller.toggle()
            self.assertEqual(calls, ['save popup', 'worker start'])
            self.assertTrue(controller.enabled)
            self.assertEqual(controller.document_path, project.resolve())
            self.assertTrue((Path(temp)/'Saved from popup_d5_textures').is_dir())


    def test_texture_companion_cache_uvs(self):
        import tempfile
        import subprocess
        import zipfile
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as temp:
            project = Path(temp) / 'Textured room.igz'
            project.write_bytes(b'test-only saved document marker')
            source = Path(temp) / 'source.png'
            image = QImage(2, 2, QImage.Format_RGBA8888)
            image.fill(QColor('#3FA9E5'))
            self.assertTrue(image.save(str(source), 'PNG'))
            folder = prepare_texture_folder(project)
            scene = Scene()
            face = triangle(scene.loose_mesh)
            face.attrs['texture'] = {'path': str(source), 'sw': 1.25, 'sh': 1.25}
            snapshot = capture_scene(scene, project, folder)
            cached = Path(snapshot['materials'][0]['diffuse_map'])
            self.assertEqual(cached.parent, project.parent/'Textured room_d5_textures')
            self.assertEqual(cached.read_bytes(), source.read_bytes())
            self.assertEqual(len(snapshot['objects'][0]['uvs']), 3)
            self.assertTrue(any(any(value != 0 for value in uv) for uv in snapshot['objects'][0]['uvs']))
            self.assertEqual(snapshot, capture_scene(scene, project, folder))
            self.assertEqual({p.name for p in folder.iterdir()}, {cached.name, adapter.MATERIAL_CACHE})


    def test_loose_geometry_and_material(self):
        scene = Scene()
        triangle(scene.loose_mesh, (1, .25, 0))
        before = scene.version
        snapshot = capture_scene(scene)
        self.assertEqual(len(snapshot['objects']), 1)
        self.assertEqual(len(snapshot['objects'][0]['triangles']), 1)
        self.assertIn([1.25, 0, 0], snapshot['objects'][0]['vertices'])
        self.assertEqual(snapshot['materials'][0]['color'], '#FF4000')
        self.assertEqual(scene.version, before)
        self.assertEqual(snapshot, capture_scene(scene))


    def test_nested_transforms_and_ids(self):
        scene = Scene()
        parent = Group(name='Parent')
        child = Group(name='Child')
        triangle(child.mesh)
        parent.xform = QMatrix4x4()
        parent.xform.translate(2,3,0)
        child.xform = QMatrix4x4()
        child.xform.translate(0,0,4)
        parent.children = [child]
        scene.groups.append(parent)
        first = capture_scene(scene)['objects'][0]
        self.assertEqual([row[3] for row in first['transform']], [2,3,4,1])
        self.assertIn(parent.uid, first['id'])
        self.assertIn(child.uid, first['id'])
        child.xform.translate(1,0,0)
        changed = capture_scene(scene)['objects'][0]
        self.assertEqual(changed['id'], first['id'])
        self.assertNotEqual(changed['transform'], first['transform'])


    def test_hidden_objects_and_removal(self):
        scene = Scene()
        group = Group(name='Hidden')
        triangle(group.mesh)
        group.hidden = True
        scene.groups.append(group)
        self.assertEqual(capture_scene(scene)['objects'], [])
        group.hidden = False
        self.assertEqual(len(capture_scene(scene)['objects']), 1)
        scene.groups.clear()
        self.assertEqual(capture_scene(scene)['objects'], [])


    def test_container_paint_and_face_override(self):
        scene = Scene()
        group = Group(name='Painted')
        triangle(group.mesh)
        group.material = {'color': (0,1,0), 'mat': 'Container Green'}
        scene.groups.append(group)
        self.assertEqual(capture_scene(scene)['materials'][0]['color'], '#00FF00')
        group.mesh.faces[0].attrs['color'] = (0,0,1)
        self.assertEqual(capture_scene(scene)['materials'][0]['color'], '#0000FF')


