"""ArUco image consumer for newly delivered ue55.rgb.Reader frames.

Prometheus Target.msg uses optical metres; aruco_tracking.cpp converts these
to body FLU. Retain that convention, with the actual calibrated mounting pose.
This module deliberately sends no flight commands and never scans recordings.
"""
import copy
import math
import re

import cv2
import numpy as np

from Simulator.ue55.rgb import config as rgb_config


def vector(value, count):
    if (not isinstance(value, list) or len(value) != count or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError('Invalid finite vector')
    return np.array(value, dtype=np.float64)


def pose(value):
    if not isinstance(value, dict) or set(value) != {'position_cm', 'quaternion_xyzw'}:
        raise ValueError('Invalid UE pose fields')
    position = vector(value['position_cm'], 3) / 100
    x, y, z, w = vector(value['quaternion_xyzw'], 4)
    if abs(x*x + y*y + z*z + w*w - 1) > 1e-6:
        raise ValueError('Non-unit quaternion')
    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    return position, rotation


class Consumer:
    """Bind only from authoritative run/View state, never from a frame.

    All limits are explicit, finite and positive. max_age_steps uses the 1 ms
    authoritative scene grid, not wall time. Call current each authority update
    even when Reader.poll returns nothing; disconnect calls invalidate.
    """
    def __init__(self, settings, *, run_id, instance_id, dictionary, marker_id,
                 side_length_m, max_age_steps, max_distance_m,
                 max_speed_mps, max_jump_m, max_reprojection_px):
        self.settings = rgb_config(settings)
        for value in (run_id, instance_id):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value):
                raise ValueError('Invalid run identity')
        if (not isinstance(dictionary, str) or
                not re.fullmatch(r'DICT_(?:[4-7]X[4-7]_(?:50|100|250|1000)|ARUCO_ORIGINAL)', dictionary) or
                not hasattr(cv2.aruco, dictionary)):
            raise ValueError('Explicit supported ArUco dictionary required')
        self.dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
        if type(marker_id) is not int or not 0 <= marker_id < len(self.dictionary.bytesList):
            raise ValueError('Tag ID outside dictionary')
        if type(max_age_steps) is not int or not 1 <= max_age_steps <= 9007199254:
            raise ValueError('Invalid target age limit')
        for value in (side_length_m, max_distance_m, max_speed_mps, max_jump_m, max_reprojection_px):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Positive finite metric limits required')
        self.run_id, self.instance_id = run_id, instance_id
        self.dictionary_name, self.marker_id, self.side_length_m = dictionary, marker_id, side_length_m
        self.max_age_steps, self.max_distance_m = max_age_steps, max_distance_m
        self.max_speed_mps, self.max_jump_m = max_speed_mps, max_jump_m
        self.max_reprojection_px = max_reprojection_px
        p = cv2.aruco.DetectorParameters()
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, p)
        s = side_length_m / 2
        self.object_points = np.array([[-s,s,0],[s,s,0],[s,-s,0],[-s,-s,0]], dtype=np.float64)
        self.epoch = self.stream_id = None
        self.generation = 0
        self.retired_streams = set()
        self.last_step = self.last_frame = self.now_step = -1
        self.target = None
        self.reason = 'unbound'

    def invalidate(self, reason='disconnected'):
        self.target = None
        self.reason = reason

    def bind(self, *, epoch, generation, stream_id, minimum_step):
        if (not isinstance(epoch, str) or not re.fullmatch('[0-9a-f]{32}', epoch) or
                not isinstance(stream_id, str) or not re.fullmatch('[0-9a-f]{32}', stream_id) or
                type(generation) is not int or generation < 1 or generation < self.generation or
                type(minimum_step) is not int or not 0 <= minimum_step <= 9007199254 or
                (generation == self.generation and epoch != self.epoch) or
                (generation == self.generation and stream_id != self.stream_id and minimum_step < self.now_step) or
                (generation > self.generation and epoch == self.epoch) or
                stream_id in self.retired_streams):
            self.invalidate('invalid_binding')
            raise ValueError('Invalid or retired authority binding')
        if (epoch, generation, stream_id) == (self.epoch, self.generation, self.stream_id):
            return
        if self.stream_id != stream_id and self.stream_id is not None:
            self.retired_streams.add(self.stream_id)
        self.epoch, self.generation, self.stream_id = epoch, generation, stream_id
        self.minimum_step = minimum_step
        self.last_step = self.last_frame = -1
        self.now_step = minimum_step
        self.invalidate('awaiting_fresh_frame')

    def current(self, now_step):
        if type(now_step) is not int or not 0 <= now_step <= 9007199254 or now_step < self.now_step:
            self.invalidate('invalid_authority_step')
            raise ValueError('Invalid or regressing authority step')
        self.now_step = now_step
        if self.target is not None and now_step > self.target['valid_until_step']:
            self.invalidate('expired')
        return copy.deepcopy(self.target)

    def _calibration(self, m):
        c = self.settings
        expected = {'encoding': 'png-rgba8-srgb',
                    'pixel_coordinates': 'image edges at 0,width/height; pixel centers at index+0.5',
                    'distortion_model': 'pinhole_zero_distortion_assumption',
                    'pose_coordinates': 'UE world centimeters; X forward Y right Z up; optical x=Y y=-Z z=X'}
        if any(m.get(k) != v for k, v in expected.items()):
            raise ValueError('Image, units or coordinate convention differs')
        if any(type(m[k]) is not int or m[k] != c[k] for k in ('width', 'height')):
            raise ValueError('Image dimensions differ')
        fov = m['horizontal_fov_degrees']
        if type(fov) not in (int, float) or not math.isfinite(fov) or abs(fov-c['horizontal_fov_degrees']) > 1e-6:
            raise ValueError('FOV differs')
        f = c['width'] / (2*math.tan(math.radians(c['horizontal_fov_degrees'])/2))
        k = vector(m['K'], 9).reshape(3, 3)
        if not np.allclose(k, [[f,0,c['width']/2],[0,f,c['height']/2],[0,0,1]], rtol=0, atol=1e-5):
            raise ValueError('Intrinsics differ from frozen camera')
        if np.any(vector(m['distortion'], 5) != 0):
            raise ValueError('Nonzero distortion unsupported')
        mount_p, mount_r = pose(m['camera_in_vehicle'])
        frozen_p, frozen_r = pose({key: c[key] for key in ('position_cm', 'quaternion_xyzw')})
        if not (np.allclose(mount_p, frozen_p, rtol=0, atol=1e-7) and
                np.allclose(mount_r, frozen_r, rtol=0, atol=1e-6)):
            raise ValueError('Extrinsics differ from frozen camera')
        world_p, world_r = pose(m['camera_world_pose'])
        return k, mount_p, mount_r, world_p, world_r

    def consume(self, frame, *, now_step):
        """Return a fresh target or None; every invalid frame clears the target.

        frame is a Reader.poll result. Its image path is the validated Reader
        path, not an arbitrary metadata-provided path. Input remains trusted
        same-process data; this is not a replacement filesystem/network reader.
        """
        self.current(now_step)
        previous = self.target
        self.invalidate('invalid_frame')
        try:
            if self.epoch is None:
                raise ValueError('Unbound authority')
            m, event = frame['metadata'], frame['notification']
            if not isinstance(m, dict) or not isinstance(event, dict):
                raise ValueError('Invalid Reader envelope')
            identity = dict(run_id=self.run_id, instance_id=self.instance_id,
                            epoch=self.epoch, stream_id=self.stream_id)
            if (any(m.get(k) != v or event.get(k) != v for k,v in identity.items()) or
                    m.get('schema') != 'wksim.rgb.v2' or event.get('schema') != 'wksim.rgb-ready.v2' or
                    type(event.get('generation')) is not int or event['generation'] != self.generation or
                    m.get('vehicle_id') != str(self.settings['vehicle_id']) or
                    m.get('sensor_id') != self.settings['sensor_id']):
                raise ValueError('Foreign frame')
            for key in ('step', 'frame_id'):
                if not isinstance(m[key], str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', m[key]):
                    raise ValueError('Invalid frame integer')
            step, frame_id = int(m['step']), int(m['frame_id'])
            if (step < self.minimum_step or step <= self.last_step or frame_id <= self.last_frame or
                    not 0 <= now_step-step <= self.max_age_steps or
                    type(m['sim_time_seconds']) not in (int, float) or m['sim_time_seconds'] != step/1000):
                raise ValueError('Old, duplicate, future or relabelled frame')
            self.last_step, self.last_frame = step, frame_id
            k, mount_p, mount_r, world_p, world_r = self._calibration(m)
            # imdecode supports Windows Unicode paths; Reader already bounded PNG size.
            with open(frame['image_path'], 'rb') as image_file:
                raw = image_file.read(self.settings['width']*self.settings['height']*5+65537)
            if len(raw) > self.settings['width']*self.settings['height']*5+65536:
                raise ValueError('Image size exceeds bound')
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None or image.dtype != np.uint8 or image.shape != (m['height'],m['width'],4):
                raise ValueError('Decoded RGBA dimensions differ')
            if np.any(image[:,:,3] != 255):
                raise ValueError('Nonopaque image')
            corners, ids, _ = self.detector.detectMarkers(cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY))
            matches = [] if ids is None else np.flatnonzero(ids.ravel() == self.marker_id)
            if len(matches) != 1:
                self.reason = 'not_detected' if len(matches) == 0 else 'ambiguous_tag_id'
                return None
            # OpenCV corners use index coordinates; UE K uses edge coordinates.
            pixels = corners[matches[0]].reshape(4,2).astype(np.float64) + 0.5
            ok, rvec, tvec = cv2.solvePnP(self.object_points, pixels, k, np.zeros(5), flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok or not np.all(np.isfinite(rvec)) or not np.all(np.isfinite(tvec)):
                raise ValueError('Pose solve failed')
            rotation = cv2.Rodrigues(rvec)[0]
            if np.any((self.object_points @ rotation.T + tvec.ravel())[:,2] <= 0):
                raise ValueError('Marker behind camera')
            projected = cv2.projectPoints(self.object_points, rvec, tvec, k, np.zeros(5))[0].reshape(4,2)
            error = float(np.sqrt(np.mean(np.sum((projected-pixels)**2,axis=1))))
            optical = tvec.ravel()
            camera_ue = optical[[2,0,1]] * [1,1,-1]
            body_flu = (mount_r @ camera_ue + mount_p) * [1,-1,1]
            world_ue = world_r @ camera_ue + world_p
            distance = float(np.linalg.norm(body_flu))
            if error > self.max_reprojection_px or distance > self.max_distance_m:
                raise ValueError('Pose quality or distance gate')
            velocity = None
            if previous is not None:
                displacement = world_ue - np.array(previous['position_world_ue_m'])
                jump = float(np.linalg.norm(displacement))
                velocity = displacement / ((step-int(previous['step']))/1000)
                if jump > self.max_jump_m or np.linalg.norm(velocity) > self.max_speed_mps:
                    raise ValueError('World target jump or speed gate')
            self.target = dict(schema='wksim.aruco-target.v1', **identity, generation=self.generation,
                               vehicle_id=m['vehicle_id'], sensor_id=m['sensor_id'], step=m['step'],
                               frame_id=m['frame_id'], sim_time_seconds=m['sim_time_seconds'],
                               dictionary=self.dictionary_name, marker_id=self.marker_id, side_length_m=self.side_length_m,
                               position_optical_m=optical.tolist(), position_body_flu_m=body_flu.tolist(),
                               position_world_ue_m=world_ue.tolist(), velocity_world_ue_mps=None if velocity is None else velocity.tolist(),
                               marker_to_optical_rvec_rad=rvec.ravel().tolist(), distance_m=distance,
                               reprojection_rms_px=error, corners_edge_px=pixels.tolist(),
                               valid_until_step=step+self.max_age_steps, opencv_version=cv2.__version__)
            self.reason = 'detected'
            return copy.deepcopy(self.target)
        except (KeyError, TypeError, ValueError, OSError, cv2.error, OverflowError) as error:
            self.invalidate('rejected: ' + str(error))
            return None
