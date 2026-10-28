# SPDX-License-Identifier: GPL-3.0-or-later
"""Native offline integration checks; these do not certify live D5 rendering."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from d5_bridge import Bridge, cube_scene, triangle_buffers, transform_array, camera_values


class BridgeTests(unittest.TestCase):
    def test_camera_axes_units_fov_and_projection_dispatch(self):
        from unittest.mock import Mock
        camera = {'position':[1,2,3], 'forward':[0,2,0], 'up':[0,0,1],
                  'horizontal_fov':60, 'orthographic':False, 'orthographic_width':4.5}
        transform, fov, width = camera_values(camera)
        self.assertEqual(transform, [200,100,300,1,0,0,0,0,1])
        self.assertEqual((fov,width), (60,450))
        fake = Bridge.__new__(Bridge)
        fake.session = object()
        fake.d = Mock()
        fake.send_camera(camera)
        fake.d.SendCameraTransformFov.assert_called_once_with(fake.session, transform,60)
        camera['orthographic'] = True
        fake.send_camera(camera)
        fake.d.D5SendCamera.assert_called_once_with(fake.session)
        fake.d.D5SetEntityFloatProperty.assert_called_with(
            fake.session,fake.d.ET_CAMERA,'','orthogonal_width',450)
        fake.session = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bridge = Bridge(self.root / 'source.igz')

    def tearDown(self):
        self.bridge.close()
        self.tmp.cleanup()

    def test_native_fractional_geometry_and_material_export(self):
        scene = cube_scene(size=1.25, color='#2B88D8')
        self.bridge.snapshot(scene)
        path = self.root / 'cube.d5a'
        self.assertTrue(self.bridge.export(path)['export_success'])
        with zipfile.ZipFile(path) as archive:
            mesh = archive.read('1.d5mesh')
            # Three consecutive triangle vertices in centimetres. Verifies
            # fractional metre coordinates survived the native API binding.
            points = [[0,0,0],[125,125,0],[0,125,0]]
            rotations = [points[i:]+points[:i] for i in range(3)]
            patterns = [struct.pack('<9f', *[v for p in tri for v in p]) for tri in rotations]
            self.assertTrue(any(pattern in mesh for pattern in patterns))
            material = archive.read('d5material.xml').decode('utf8')
            self.assertIn('2B88D8', material)
        self.assertNotIn('bpy', sys.modules)

    def test_native_default_material_exports_white(self):
        scene = cube_scene()
        scene['materials'] = []
        scene['objects'][0].pop('material_id')
        self.bridge.snapshot(scene)
        path = self.root / 'default-white.d5a'
        self.assertTrue(self.bridge.export(path)['export_success'])
        with zipfile.ZipFile(path) as archive:
            material = archive.read('d5material.xml').decode('utf8')
            self.assertIn('FFFFFF', material)
            self.assertNotIn('CCCCCC', material)
            self.assertIn('<Metallic>0</Metallic>', material)
            self.assertIn('<Specular>0.5</Specular>', material)

    def test_incremental_noop_move_resize_material_delete_restore(self):
        first = self.bridge.snapshot(cube_scene())
        self.assertEqual(first['changed'], 1)
        self.assertEqual(first['native_instances'], 1)
        self.assertEqual(self.bridge.snapshot(cube_scene())['changed'], 0)
        moved = self.bridge.snapshot(cube_scene(x=2.25))
        self.assertEqual(moved['changed'], 1)
        self.assertEqual(moved['native_instances'], 1)
        resized = self.bridge.snapshot(cube_scene(x=2.25, size=1.5))
        self.assertEqual(resized['changed'], 1)
        self.assertEqual(resized['native_instances'], 1)
        result = self.bridge.snapshot(cube_scene(x=2.25, size=1.5, color='#112233'))
        self.assertEqual(result['changed'], 0)
        self.assertEqual(result['materials_changed'], 1)
        deleted = self.bridge.snapshot({'objects': []})
        self.assertEqual(deleted['removed'], 1)
        self.assertEqual(deleted['native_instances'], 0)
        self.assertEqual(self.bridge.snapshot(cube_scene())['changed'], 1)

    def test_invalid_snapshot_does_not_erase_acknowledged_scene(self):
        self.bridge.snapshot(cube_scene())
        previous = dict(self.bridge.hashes)
        scene = cube_scene()
        scene['objects'][0]['triangles'][0][0] = 999
        with self.assertRaisesRegex(ValueError, 'outside vertex'):
            self.bridge.snapshot(scene)
        self.assertEqual(self.bridge.hashes, previous)

    def test_source_ids_are_isolated(self):
        other = Bridge(self.root / 'other.igz')
        try:
            self.assertNotEqual(self.bridge.identifier('node', 'a'), other.identifier('node', 'a'))
        finally:
            other.close()

    def test_d5_transform_conversion(self):
        matrix = [[1,0,0,2.25],[0,1,0,3.5],[0,0,1,4.75],[0,0,0,1]]
        self.assertEqual(transform_array(matrix),
                         [1,0,0,0,0,1,0,0,0,0,1,0,350,225,475,1])

    def test_mesh_axes_normals_and_clockwise_winding_agree(self):
        import numpy as np
        obj = {'vertices':[[0,0,0],[2,0,0],[0,0,1]], 'triangles':[[0,1,2]]}
        coords, normals, *_ = triangle_buffers(obj)
        points = coords.reshape(-1,3)
        self.assertEqual(points.tolist(), [[0,0,0],[0,2,0],[0,0,1]])
        self.assertEqual(normals.reshape(-1,3).tolist(), [[-1,0,0]]*3)
        # Outward normals agree with CW front faces in D5's left-handed axes.
        cross = np.cross(points[1]-points[0], points[2]-points[0])
        self.assertLess(float(np.dot(cross, normals[:3])), 0)

    def test_supplied_smooth_normals_survive_axes_mapping_and_native_export(self):
        import numpy as np
        obj = {'id':'curved', 'vertices':[[0,0,0],[2,0,0],[0,0,1]],
               'triangles':[[0,1,2]], 'normals':[[0,-1,1],[0,-1,1],[0,-1,0]]}
        _, normals, *_ = triangle_buffers(obj)
        expected = [[-1/2**.5,0,1/2**.5],[-1/2**.5,0,1/2**.5],[-1,0,0]]
        self.assertTrue(np.allclose(normals.reshape(-1,3),expected))
        self.bridge.snapshot({'objects':[obj]})
        path = self.root/'smooth-normals.d5a'
        self.assertTrue(self.bridge.export(path)['export_success'])
        with zipfile.ZipFile(path) as archive:
            mesh = archive.read('1.d5mesh')
            # The native file serializer converts the on-wire X/Y axes back;
            # the source's tilted normal must survive instead of becoming flat.
            self.assertTrue(struct.pack('<3f',0,-1/2**.5,1/2**.5) in mesh)
        previous = dict(self.bridge.hashes)
        obj['normals'][0] = [0,0,0]
        with self.assertRaisesRegex(ValueError,'nonzero'):
            self.bridge.snapshot({'objects':[obj]})
        self.assertEqual(self.bridge.hashes,previous)
        obj['normals'] = [[0,0,1]]
        with self.assertRaisesRegex(ValueError,'one per vertex'):
            triangle_buffers(obj)

    def test_rotated_group_world_position_matches_camera_axes_without_mirroring(self):
        import numpy as np
        source = [[0,-1,0,2],[1,0,0,3],[0,0,1,4],[0,0,0,1]]
        converted = np.array(transform_array(source)).reshape(4,4).T
        # Source point (1,2,3) becomes world (0,4,7), then D5 (4,0,7).
        point = converted @ np.array([200,100,300,1])
        self.assertTrue(np.allclose(point, [400,0,700,1]))
        self.assertAlmostEqual(float(np.linalg.det(converted[:3,:3])), 1)

    def test_stdio_protocol_with_real_native_module(self):
        worker = Path(__file__).with_name('d5_bridge.py')
        requests = [{'op': 'info'}, {'op': 'snapshot', 'scene': cube_scene(size=1.25)},
                    {'op': 'export', 'path': str(self.root / 'stdio.d5a')}, {'op': 'quit'}]
        result = subprocess.run([sys.executable, str(worker), '--stdio', '--source',
                                 str(self.root / 'stdio.igz'), '--output', str(self.root / 'worker.json')],
                                input=''.join(json.dumps(r)+'\n' for r in requests),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r['op'] for r in replies], ['info', 'snapshot', 'export'])
        self.assertTrue(all(r['ok'] for r in replies))
        self.assertFalse(replies[0]['blender_imported'])
        self.assertTrue(replies[2]['export_success'])


if __name__ == '__main__':
    unittest.main()
