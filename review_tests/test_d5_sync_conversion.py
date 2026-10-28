# SPDX-License-Identifier: GPL-3.0-or-later
"""Native-independent conversion checks for the optional D5 example."""
import importlib.util
from pathlib import Path
import unittest

_path = Path(__file__).resolve().parents[1]/'ingetrazo_d5_sync/d5_bridge.py'
_spec = importlib.util.spec_from_file_location('d5_bridge_test', _path)
_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bridge)
Bridge = _bridge.Bridge
triangle_buffers = _bridge.triangle_buffers
transform_array = _bridge.transform_array
camera_values = _bridge.camera_values

class TestD5Conversion(unittest.TestCase):
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


    def test_d5_transform_conversion(self):
        matrix = [[1,0,0,2.25],[0,1,0,3.5],[0,0,1,4.75],[0,0,0,1]]
        self.assertEqual(transform_array(matrix),
                         [1,0,0,0,0,1,0,0,0,0,1,0,225,350,475,1])


    def test_mesh_axes_normals_and_clockwise_winding_agree(self):
        import numpy as np
        obj = {'vertices':[[0,0,0],[2,0,0],[0,0,1]], 'triangles':[[0,1,2]]}
        coords, normals, *_ = triangle_buffers(obj)
        points = coords.reshape(-1,3)
        self.assertEqual(points.tolist(), [[0,0,0],[2,0,0],[0,0,1]])
        self.assertEqual(normals.reshape(-1,3).tolist(), [[0,-1,0]]*3)
        # Input is right-handed; native export verifies the SDK conversion.
        cross = np.cross(points[1]-points[0], points[2]-points[0])
        self.assertGreater(float(np.dot(cross, normals[:3])), 0)


    def test_rotated_group_world_position_matches_camera_axes_without_mirroring(self):
        import numpy as np
        source = [[0,-1,0,2],[1,0,0,3],[0,0,1,4],[0,0,0,1]]
        converted = np.array(transform_array(source)).reshape(4,4).T
        # Source point (1,2,3) becomes world (0,4,7) before SDK conversion.
        point = converted @ np.array([100,200,300,1])
        self.assertTrue(np.allclose(point, [0,400,700,1]))
        self.assertAlmostEqual(float(np.linalg.det(converted[:3,:3])), 1)


