"""Optional joint RGB config and current-epoch UDP notification consumer.

No directory replay, flight commands, consumer ACK, or connection to physics.
"""
import json
import math
from pathlib import Path
import re
import socket
import struct


def config(value):
    keys = {'version', 'vehicle_id', 'sensor_id', 'width', 'height',
            'horizontal_fov_degrees', 'position_cm', 'quaternion_xyzw',
            'interval_steps', 'notify_port'}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('RGB config fields differ')
    for key, low, high in (('version', 1, 1), ('vehicle_id', 1, 2),
                           ('width', 16, 4096), ('height', 16, 4096),
                           ('interval_steps', 1, 60000), ('notify_port', 1024, 65535)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError('Invalid RGB ' + key)
    if value['notify_port'] == 19060 or value['width'] * value['height'] > 4194304:
        raise ValueError('RGB port/image bounds exceeded')
    if not isinstance(value['sensor_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value['sensor_id']):
        raise ValueError('Invalid RGB sensor identity')
    def numbers(items, count):
        return (isinstance(items, list) and len(items) == count and
                all(type(v) in (int, float) and math.isfinite(v) for v in items))
    fov = value['horizontal_fov_degrees']
    if type(fov) not in (int, float) or not math.isfinite(fov) or not 5 <= fov <= 150:
        raise ValueError('Invalid RGB horizontal FOV')
    if not numbers(value['position_cm'], 3) or max(map(abs, value['position_cm'])) > 1e9:
        raise ValueError('Invalid RGB extrinsic position')
    if not numbers(value['quaternion_xyzw'], 4) or abs(sum(v*v for v in value['quaternion_xyzw'])-1) > 1e-6:
        raise ValueError('Invalid RGB extrinsic quaternion')
    return json.loads(json.dumps(value, allow_nan=False))


class Reader:
    """Bind before View.start; set_epoch only from the authoritative run status.

    poll returns newly notified frames. Stop polling or close to disconnect;
    rebind with a new Reader to reconnect without discovering historical files.
    """
    def __init__(self, directory, run_id, instance_id, settings, *, stream_id):
        self.config = config(settings)
        self.directory = Path(directory).resolve()
        self.run_id, self.instance_id = run_id, instance_id
        if not isinstance(stream_id,str) or not re.fullmatch('[0-9a-f]{32}',stream_id):
            raise ValueError('Explicit current RGB producer stream identity required')
        self.stream_id=stream_id
        self.epoch, self.generation = None, 0
        self.last_step = self.last_frame = -1
        self.minimum_step=0
        self.rejected = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(('127.0.0.1', self.config['notify_port']))
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close()
            raise

    def set_epoch(self, epoch, generation, *, minimum_step=0):
        """On a new binding, discard captures begun before this authority step.

        Repeated calls for the same epoch do not chase the current step; normal
        asynchronous capture/readback latency remains observable in metadata.
        """
        if (not isinstance(epoch, str) or not re.fullmatch('[0-9a-f]{32}', epoch) or
                type(generation) is not int or generation < 1 or generation < self.generation or
                type(minimum_step) is not int or not 0<=minimum_step<=9007199254 or
                (generation == self.generation and epoch != self.epoch) or
                (generation > self.generation and epoch == self.epoch)):
            raise ValueError('Invalid or retired RGB epoch')
        if generation > self.generation:
            self.epoch, self.generation = epoch, generation
            self.last_step = self.last_frame = -1
            self.minimum_step=minimum_step

    def _read(self, event):
        expected = dict(schema='wksim.rgb-ready.v2', run_id=self.run_id,
                        instance_id=self.instance_id, epoch=self.epoch, generation=self.generation,stream_id=self.stream_id)
        if not isinstance(event, dict) or set(event) != set(expected) | {'metadata'} or any(event[k] != v for k,v in expected.items()):
            raise ValueError('Foreign RGB notification')
        name = event['metadata']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.json', name):
            raise ValueError('Invalid metadata filename')
        path = self.directory / name
        if path.is_symlink() or path.stat().st_size > 16384:
            raise ValueError('Invalid metadata file')
        data = json.loads(path.read_text(encoding='utf-8'))
        identity = dict(schema='wksim.rgb.v2', run_id=self.run_id, instance_id=self.instance_id,stream_id=self.stream_id,
                        epoch=self.epoch, vehicle_id=str(self.config['vehicle_id']), sensor_id=self.config['sensor_id'])
        if any(data.get(k) != v for k,v in identity.items()):
            raise ValueError('Foreign RGB metadata')
        for field in ('step', 'frame_id'):
            if not isinstance(data[field], str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', data[field]):
                raise ValueError('Invalid RGB integer identity')
        step, frame = int(data['step']), int(data['frame_id'])
        if (step < self.minimum_step or step <= self.last_step or frame <= self.last_frame or
                type(data['sim_time_seconds']) not in (int,float) or data['sim_time_seconds'] != step / 1000):
            raise ValueError('Repeated, old or relabelled RGB frame')
        if (data['width'], data['height']) != (self.config['width'], self.config['height']):
            raise ValueError('Unexpected image dimensions')
        image = data['image']
        if image != path.stem + '.png':
            raise ValueError('Image escapes metadata identity')
        image_path = self.directory / image
        if image_path.is_symlink() or image_path.stat().st_size > self.config['width'] * self.config['height'] * 5 + 65536:
            raise ValueError('Invalid RGB image file')
        with image_path.open('rb') as stream:
            header = stream.read(24)
        if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR' or struct.unpack('>II', header[16:24]) != (data['width'],data['height']):
            raise ValueError('Image format/dimensions differ')
        self.last_step, self.last_frame = step, frame
        return dict(notification=event, metadata=data, metadata_path=str(path), image_path=str(image_path))

    def poll(self):
        frames = []
        for _ in range(64):
            try:
                raw, sender = self.socket.recvfrom(8192)
            except BlockingIOError:
                break
            try:
                if sender[0] != '127.0.0.1' or self.epoch is None:
                    raise ValueError('RGB source/epoch unavailable')
                frames.append(self._read(json.loads(raw)))
            except (OSError, ValueError, KeyError, TypeError, struct.error):
                self.rejected += 1
        return frames

    def close(self):
        self.socket.close()
