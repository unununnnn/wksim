"""Offline depth contracts: real UDP admission with synthetic bytes; no rendering claim."""
import copy
import json
import math
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.ue55.depth import Reader, cloud
from tools.audit_depth_geometry import compare, expected


class DepthTests(unittest.TestCase):
    def test_notifications_cloud_and_retirement(self):
        with tempfile.TemporaryDirectory() as directory:
            port_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            port_socket.bind(('127.0.0.1', 0)); port = port_socket.getsockname()[1]; port_socket.close()
            settings = dict(version=1, vehicle_id=1, sensor_id='depth', width=16, height=16,
                            horizontal_fov_degrees=90, position_cm=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1],
                            interval_steps=100, notify_port=port, max_depth_meters=100)
            stream, epoch = 'a'*32, 'b'*32
            reader = Reader(directory, 'run', 'i'*32, settings, stream_id=stream)
            try:
                reader.set_epoch(epoch, 1, minimum_step=100)
                stem = f'depth_{stream}_1'
                meta = dict(schema='wksim.depth.v1', run_id='run', instance_id='i'*32, epoch=epoch,
                            generation=1, stream_id=stream, vehicle_id='1', sensor_id='depth', step='100', frame_id='1',
                            sim_time_seconds=.1, encoding='float32-le-meters', depth_semantics='optical_plane_z',
                            width=16, height=16, horizontal_fov_degrees=90, max_depth_meters=100,
                            K=[8, 0, 8, 0, 8, 8, 0, 0, 1], image=stem+'.f32',
                            camera_in_vehicle=dict(position_cm=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1]),
                            camera_world_pose=dict(position_cm=[100, 200, 300], quaternion_xyzw=[0, 0, 0, 1]))
                path = Path(directory)/meta['image']; depths = [2.]*256; depths[0] = float('nan')
                path.write_bytes(struct.pack('<256f', *depths))
                metadata = Path(directory)/(stem+'.json'); metadata.write_text(json.dumps(meta))
                event = {k: meta[k] for k in ('run_id', 'instance_id', 'epoch', 'generation', 'stream_id')}
                event.update(schema='wksim.depth-ready.v1', metadata=metadata.name)
                sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sender.sendto(json.dumps(event).encode(), ('127.0.0.1', port))
                    frame = reader.poll()[0]
                finally:
                    sender.close()
                self.assertEqual(len(frame['point_cloud']['points']), 255)
                self.assertEqual(frame['valid_mask'][0], 0)
                # Pixel 8,8: optical right .125m/down .125m, UE forward 2m.
                point = next(p for p in frame['point_cloud']['points'] if p[0] == 136)
                self.assertEqual(point, [136, 2.125, 3., 2.875])
                with self.assertRaises(ValueError): reader._read(event)
                reader.set_epoch('c'*32, 2, minimum_step=200)
                with self.assertRaises(ValueError): reader._read(event)
                with self.assertRaises(ValueError): reader.set_epoch(epoch, 1)
                fresh = Reader(directory, 'run', 'i'*32, dict(settings, notify_port=port+1), stream_id=stream)
                try:
                    fresh.set_epoch(epoch, 1, minimum_step=101)
                    with self.assertRaises(ValueError): fresh._read(event)
                finally:
                    fresh.close()
                bad = copy.deepcopy(meta); bad['camera_world_pose']['quaternion_xyzw'] = [0, 0, 0, 2]
                with self.assertRaises(ValueError): cloud(bad, depths)
                with self.assertRaises(ValueError): cloud(meta, [float('inf')]*256)
            finally:
                reader.close()

    def test_box_plane_occlusion_and_invalid_oracle(self):
        fixture = dict(objects=[dict(name=name, visible=True, position_cm=p, scale=[1, 1, 1],
                       quaternion_xyzw=[0, 0, 0, 1], mesh_bounds_min=[-v/2 for v in size],
                       mesh_bounds_max=[v/2 for v in size]) for name, p, size in (
                       ('plane', [400, 0, 100], [1, 160, 160]),
                       ('box', [350, 0, 100], [30, 40, 180]))])
        meta = dict(width=160, height=120, K=[80, 0, 80, 0, 80, 60, 0, 0, 1], max_depth_meters=100,
                    camera_world_pose=dict(position_cm=[30, 0, 100], quaternion_xyzw=[0, 0, 0, 1]))
        values = [v[0] for v in expected(meta, fixture)]
        self.assertAlmostEqual(values[60*160+80], 3.05)  # front of the near box, not the plane
        self.assertTrue(math.isnan(values[0]))
        self.assertEqual(compare(meta, values, fixture)['distance_coverage'], 1)
        wrong = [v*100 for v in values]
        with self.assertRaises(ValueError): compare(meta, wrong, fixture)
        with self.assertRaises(ValueError): compare(meta, [0 if math.isnan(v) else v for v in values], fixture)
        # A shifted occluder must not fit the same ray intersections.
        shifted = copy.deepcopy(fixture); shifted['objects'][1]['position_cm'][1] += 80
        with self.assertRaises(ValueError): compare(meta, values, shifted)
        rotated = copy.deepcopy(meta)
        rotated['camera_world_pose']['quaternion_xyzw'] = [0, 0, math.sin(.1), math.cos(.1)]
        values = [v[0] for v in expected(rotated, fixture)]
        self.assertEqual(compare(rotated, values, fixture)['distance_coverage'], 1)


if __name__ == '__main__':
    unittest.main()
