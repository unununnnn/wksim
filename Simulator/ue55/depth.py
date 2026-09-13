"""Bounded depth notification reader and indexed ENU point-cloud export.

Uses RGB's proven socket/epoch admission; no directory replay or physics ACK.
"""
import json
import math
from pathlib import Path
import re
import struct

from .rgb import Reader as RgbReader, config as rgb_config


def config(value):
    if not isinstance(value, dict) or 'max_depth_meters' not in value:
        raise ValueError('Depth max_depth_meters required')
    base = rgb_config({k: v for k, v in value.items() if k != 'max_depth_meters'})
    maximum = value['max_depth_meters']
    if (type(maximum) not in (int, float) or not math.isfinite(maximum) or
            not 0 < maximum <= 1000 or base['width'] > 640 or base['height'] > 480):
        raise ValueError('Depth range/resolution bounds exceeded')
    return dict(base, max_depth_meters=maximum)


def rotate(q, v):
    x, y, z, w = q
    a = [y*v[2]-z*v[1], z*v[0]-x*v[2], x*v[1]-y*v[0]]
    b = [y*a[2]-z*a[1], z*a[0]-x*a[2], x*a[1]-y*a[0]]
    return [v[i]+2*w*a[i]+2*b[i] for i in range(3)]


def pose(value):
    if not isinstance(value, dict) or set(value) != {'position_cm', 'quaternion_xyzw'}:
        raise ValueError('Invalid depth pose fields')
    p, q = value['position_cm'], value['quaternion_xyzw']
    for items, count in ((p, 3), (q, 4)):
        if (not isinstance(items, list) or len(items) != count or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in items)):
            raise ValueError('Invalid depth pose numbers')
    if max(map(abs, p)) > 1e9 or abs(sum(v*v for v in q)-1) > 1e-6:
        raise ValueError('Invalid depth unit pose')
    return p, q


def cloud(metadata, depths):
    """Each point has an index; all points inherit this envelope's sampling identity."""
    p, q = pose(metadata['camera_world_pose'])
    k, width = metadata['K'], metadata['width']
    points, mask = [], bytearray(len(depths))
    for index, z in enumerate(depths):
        if math.isnan(z):
            continue
        if not math.isfinite(z) or not 0 < z < metadata['max_depth_meters']:
            raise ValueError('Invalid finite depth; producer must encode NaN')
        v, u = divmod(index, width)
        local = [z, (u+.5-k[2])*z/k[0], -(v+.5-k[5])*z/k[4]]
        world = [a+b/100 for a, b in zip(rotate(q, local), p)]
        points.append([index, world[1], world[0], world[2]])
        mask[index] = 1
    identity = {k: metadata[k] for k in ('run_id', 'instance_id', 'epoch', 'generation',
                'stream_id', 'vehicle_id', 'sensor_id', 'step', 'frame_id', 'sim_time_seconds')}
    return dict(schema='wksim.depth-cloud.v1', identity=identity, frame='map_ENU', unit='m',
                fields=['pixel_index', 'east', 'north', 'up'], points=points), bytes(mask)


class Reader(RgbReader):
    def __init__(self, directory, run_id, instance_id, settings, *, stream_id):
        checked = config(settings)
        super().__init__(directory, run_id, instance_id,
                         {k: v for k, v in checked.items() if k != 'max_depth_meters'}, stream_id=stream_id)
        self.config = checked

    def _read(self, event):
        expected = dict(schema='wksim.depth-ready.v1', run_id=self.run_id,
                        instance_id=self.instance_id, epoch=self.epoch,
                        generation=self.generation, stream_id=self.stream_id)
        if (not isinstance(event, dict) or set(event) != set(expected) | {'metadata'} or
                any(event[k] != v for k, v in expected.items())):
            raise ValueError('Foreign depth notification')
        name = event['metadata']
        if not isinstance(name, str) or not re.fullmatch(r'depth_[0-9a-f]{32}_[1-9][0-9]*\.json', name):
            raise ValueError('Invalid depth filename')
        path = self.directory / name
        if path.is_symlink() or path.stat().st_size > 16384:
            raise ValueError('Invalid depth metadata file')
        data = json.loads(path.read_text(encoding='utf-8'))
        identity = dict(expected, schema='wksim.depth.v1', vehicle_id=str(self.config['vehicle_id']),
                        sensor_id=self.config['sensor_id'], encoding='float32-le-meters',
                        depth_semantics='optical_plane_z')
        if any(data.get(k) != v for k, v in identity.items()):
            raise ValueError('Foreign depth metadata')
        for key in ('step', 'frame_id'):
            if not isinstance(data[key], str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', data[key]):
                raise ValueError('Invalid depth integer identity')
        step, frame = int(data['step']), int(data['frame_id'])
        if (step < self.minimum_step or step <= self.last_step or frame <= self.last_frame or
                type(data['sim_time_seconds']) not in (int, float) or data['sim_time_seconds'] != step/1000):
            raise ValueError('Repeated, retired or relabelled depth frame')
        for key in ('width', 'height', 'horizontal_fov_degrees', 'max_depth_meters'):
            if type(data[key]) not in (int, float) or data[key] != self.config[key]:
                raise ValueError('Unexpected depth calibration')
        w, h = self.config['width'], self.config['height']
        focal = w/(2*math.tan(math.radians(self.config['horizontal_fov_degrees'])/2))
        k = data['K']
        if (not isinstance(k, list) or len(k) != 9 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in k) or
                math.dist(k, [focal, 0, w/2, 0, focal, h/2, 0, 0, 1]) > 1e-5):
            raise ValueError('Unexpected depth intrinsics')
        pose(data['camera_world_pose'])
        pose(data['camera_in_vehicle'])
        if data['camera_in_vehicle'] != {k: self.config[k] for k in ('position_cm', 'quaternion_xyzw')}:
            raise ValueError('Unexpected depth mount')
        image = data['image']
        if name != f'depth_{self.stream_id}_{frame}.json' or image != path.stem+'.f32':
            raise ValueError('Depth filename differs from identity')
        image_path = self.directory / image
        if image_path.is_symlink() or image_path.stat().st_size != w*h*4:
            raise ValueError('Invalid depth byte count')
        depths = [v[0] for v in struct.iter_unpack('<f', image_path.read_bytes())]
        point_cloud, mask = cloud(data, depths)
        self.last_step, self.last_frame = step, frame
        return dict(notification=event, metadata=data, metadata_path=str(path), image_path=str(image_path),
                    depths=depths, point_cloud=point_cloud, valid_mask=mask)
