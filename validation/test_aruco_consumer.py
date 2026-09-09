"""Deterministic code-generated images only; no UE, ROS, FC or flight.

Run: work/dependencies/aruco-python/Scripts/python.exe -m unittest validation.test_aruco_consumer -v
Optional small evidence: ... -m validation.test_aruco_consumer --evidence validation/aruco-consumer-20260909
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from Simulator.wksim_perception.aruco import Consumer
from Simulator.ue55.rgb import Reader


SETTINGS = dict(version=1, vehicle_id=2, sensor_id='forward', width=640, height=480,
                horizontal_fov_degrees=90, position_cm=[30,20,10], quaternion_xyzw=[0,0,0,1],
                interval_steps=100, notify_port=19992)
LIMITS = dict(run_id='fixture-run', instance_id='fixture-instance', dictionary='DICT_6X6_250',
              marker_id=23, side_length_m=0.5, max_age_steps=300, max_distance_m=8,
              max_speed_mps=2, max_jump_m=0.5, max_reprojection_px=1)


def consumer(settings=None, **overrides):
    c = Consumer(settings or SETTINGS, **(LIMITS | overrides))
    c.bind(epoch='a'*32, generation=1, stream_id='b'*32, minimum_step=1000)
    return c


def fixture(directory, *, step=1000, frame_id=1, translation=(0.12,0.04,2.0),
            rotation=(math.pi,0.12,0.1), marker_id=23, dictionary='DICT_6X6_250',
            settings=None, occluded=False, blank=False, duplicate=False,
            epoch='a'*32, generation=1, stream_id='b'*32, world_pose=None):
    c = settings or SETTINGS
    f = c['width'] / (2*math.tan(math.radians(c['horizontal_fov_degrees'])/2))
    k = np.array([[f,0,c['width']/2],[0,f,c['height']/2],[0,0,1]],np.float64)
    points = np.array([[-.25,.25,0],[.25,.25,0],[.25,-.25,0],[-.25,-.25,0]],np.float64)
    pixels = cv2.projectPoints(points,np.array(rotation,np.float64),np.array(translation,np.float64),k,np.zeros(5))[0].reshape(4,2)
    marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,dictionary)),marker_id,400)
    source = np.array([[-.5,-.5],[399.5,-.5],[399.5,399.5],[-.5,399.5]],np.float32)
    image = cv2.warpPerspective(marker,cv2.getPerspectiveTransform(source,(pixels-.5).astype(np.float32)),
                               (c['width'],c['height']),flags=cv2.INTER_NEAREST,borderValue=255)
    if occluded:
        x, y = np.mean(pixels,axis=0).astype(int)
        image[y-15:y+15,x-50:x+50] = 255
    if blank:
        image[:] = 255
    if duplicate:
        image[30:110,30:110] = cv2.resize(marker,(80,80),interpolation=cv2.INTER_NEAREST)
    rgba = cv2.cvtColor(image,cv2.COLOR_GRAY2BGRA)
    name = f'rgb_{stream_id}_{frame_id}'
    path = Path(directory)/f'{name}.png'
    path.write_bytes(cv2.imencode('.png',rgba)[1].tobytes())
    identity = dict(run_id=LIMITS['run_id'],instance_id=LIMITS['instance_id'],epoch=epoch,stream_id=stream_id)
    m = dict(schema='wksim.rgb.v2',**identity,vehicle_id=str(c['vehicle_id']),sensor_id=c['sensor_id'],
             step=str(step),frame_id=str(frame_id),sim_time_seconds=step/1000,image=path.name,
             encoding='png-rgba8-srgb',width=c['width'],height=c['height'],horizontal_fov_degrees=c['horizontal_fov_degrees'],
             K=k.ravel().tolist(),distortion=[0,0,0,0,0],distortion_model='pinhole_zero_distortion_assumption',
             pixel_coordinates='image edges at 0,width/height; pixel centers at index+0.5',
             pose_coordinates='UE world centimeters; X forward Y right Z up; optical x=Y y=-Z z=X',
             camera_in_vehicle={key:c[key] for key in ('position_cm','quaternion_xyzw')},
             camera_world_pose=world_pose or dict(position_cm=[0,0,0],quaternion_xyzw=[0,0,0,1]))
    metadata_path = path.with_suffix('.json')
    metadata_path.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    event = dict(schema='wksim.rgb-ready.v2',**identity,generation=generation,metadata=metadata_path.name)
    return dict(metadata=m,notification=event,image_path=str(path),metadata_path=str(metadata_path))


class ArucoConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aruco-')
        self.addCleanup(self.temp.cleanup)
        self.c = consumer()

    def frame(self, **kwargs):
        return fixture(self.temp.name,**kwargs)

    def detected(self):
        result = self.c.consume(self.frame(),now_step=1000)
        self.assertIsNotNone(result,self.c.reason)
        return result

    def test_pose_body_axes_and_metric_units(self):
        result = self.detected()
        np.testing.assert_allclose(result['position_optical_m'],[.12,.04,2],atol=.035)
        np.testing.assert_allclose(result['position_body_flu_m'],[2.3,-.32,.06],atol=.035)
        self.assertLess(result['reprojection_rms_px'],1)
        self.assertEqual(result['step'],'1000')
        self.assertEqual(result['stream_id'],'b'*32)
        self.assertIsNone(result['velocity_world_ue_mps'])

    def test_rotated_mount_and_world_pose(self):
        settings = SETTINGS | dict(quaternion_xyzw=[0,0,math.sin(math.pi/4),math.cos(math.pi/4)])
        c = consumer(settings)
        result = c.consume(self.frame(settings=settings,world_pose=dict(position_cm=[100,200,300],quaternion_xyzw=[0,0,0,1])),now_step=1000)
        self.assertIsNotNone(result,c.reason)
        np.testing.assert_allclose(result['position_body_flu_m'],[.18,-2.2,.06],atol=.035)
        np.testing.assert_allclose(result['position_world_ue_m'],[3,2.12,2.96],atol=.035)

    def test_lost_occluded_and_fresh_recovery(self):
        self.detected()
        self.assertIsNone(self.c.consume(self.frame(step=1100,frame_id=2,occluded=True),now_step=1100))
        self.assertEqual(self.c.reason,'not_detected')
        self.assertIsNone(self.c.current(1100))
        result = self.c.consume(self.frame(step=1200,frame_id=3,translation=(.4,.04,2)),now_step=1200)
        self.assertIsNotNone(result,self.c.reason)
        self.assertIsNone(result['velocity_world_ue_mps'])
        self.assertIsNone(self.c.consume(self.frame(step=1300,frame_id=4,blank=True),now_step=1300))

    def test_wrong_id_dictionary_and_duplicate_tag(self):
        for kwargs in (dict(marker_id=24),dict(dictionary='DICT_5X5_250'),dict(duplicate=True)):
            with self.subTest(kwargs=kwargs):
                c = consumer()
                self.assertIsNone(c.consume(self.frame(**kwargs),now_step=1000))
                self.assertIn(c.reason,('not_detected','ambiguous_tag_id'))

    def test_foreign_duplicate_old_future_rejected_and_clear(self):
        mutations = [('metadata','run_id','other'),('metadata','instance_id','other'),
                     ('metadata','epoch','c'*32),('metadata','stream_id','c'*32),
                     ('metadata','vehicle_id','1'),('metadata','sensor_id','other'),
                     ('notification','generation',2),('notification','stream_id','c'*32),
                     ('metadata','step','1000'),('metadata','frame_id','1'),
                     ('metadata','sim_time_seconds',1.234),('metadata','step','1200')]
        for section,key,value in mutations:
            with self.subTest(key=key,value=value):
                c=consumer()
                self.assertIsNotNone(c.consume(self.frame(),now_step=1000))
                frame=self.frame(step=1100,frame_id=2)
                frame[section][key]=value
                self.assertIsNone(c.consume(frame,now_step=1100))
                self.assertIsNone(c.current(1100))

    def test_freshness_on_no_frames_and_regression(self):
        result=self.detected()
        result['position_body_flu_m'][0]=999
        self.assertNotEqual(self.c.current(1300)['position_body_flu_m'][0],999)
        self.assertIsNone(self.c.current(1301))
        self.assertEqual(self.c.reason,'expired')
        self.assertIsNone(self.c.consume(self.frame(step=1001,frame_id=2),now_step=1400))
        with self.assertRaises(ValueError): self.c.current(1200)

    def test_new_stream_epoch_and_retirement(self):
        self.detected()
        self.c.bind(epoch='a'*32,generation=1,stream_id='c'*32,minimum_step=1100)
        self.assertIsNone(self.c.current(1100))
        self.assertIsNone(self.c.consume(self.frame(step=1100,frame_id=2),now_step=1100))
        result=self.c.consume(self.frame(step=1200,frame_id=1,stream_id='c'*32),now_step=1200)
        self.assertIsNotNone(result,self.c.reason)
        self.assertIsNone(result['velocity_world_ue_mps'])
        with self.assertRaises(ValueError): self.c.bind(epoch='a'*32,generation=1,stream_id='b'*32,minimum_step=1200)
        self.c.bind(epoch='d'*32,generation=2,stream_id='c'*32,minimum_step=0)
        result=self.c.consume(self.frame(step=100,frame_id=1,epoch='d'*32,generation=2,stream_id='c'*32),now_step=100)
        self.assertIsNotNone(result,self.c.reason)
        with self.assertRaises(ValueError): self.c.bind(epoch='a'*32,generation=1,stream_id='e'*32,minimum_step=0)

    def test_calibration_units_and_pose_rejections(self):
        mutations=dict(K=[320,0,0,0,320,240,0,0,1],distortion=[.1,0,0,0,0],
                       pixel_coordinates='integer centers',pose_coordinates='NED metres',
                       encoding='bgr8',width=True,horizontal_fov_degrees=91,
                       camera_in_vehicle=dict(position_cm=[31,20,10],quaternion_xyzw=[0,0,0,1]),
                       camera_world_pose=dict(position_cm=[0,0,float('nan')],quaternion_xyzw=[0,0,0,1]))
        for key,value in mutations.items():
            with self.subTest(key=key):
                c=consumer()
                self.assertIsNotNone(c.consume(self.frame(),now_step=1000))
                frame=self.frame(step=1100,frame_id=2)
                frame['metadata'][key]=value
                self.assertIsNone(c.consume(frame,now_step=1100))
                self.assertIsNone(c.current(1100))

    def test_explicit_configuration_validation(self):
        for values in (dict(dictionary='bad'),dict(marker_id=250),dict(marker_id=True),
                       dict(side_length_m=0),dict(side_length_m=float('nan')),
                       dict(max_age_steps=True),dict(max_speed_mps=-1)):
            with self.subTest(values=values),self.assertRaises(ValueError): consumer(**values)

    def test_movement_speed_jump_distance_and_disconnect(self):
        self.detected()
        result=self.c.consume(self.frame(step=1100,frame_id=2,translation=(.15,.04,2)),now_step=1100)
        self.assertIsNotNone(result,self.c.reason)
        np.testing.assert_allclose(result['velocity_world_ue_mps'],[0,.3,0],atol=.12)
        self.assertIsNone(self.c.consume(self.frame(step=1200,frame_id=3,translation=(.5,.04,2)),now_step=1200))
        self.assertIn('speed gate',self.c.reason)
        c=consumer(max_jump_m=.1,max_speed_mps=100)
        self.assertIsNotNone(c.consume(self.frame(),now_step=1000))
        self.assertIsNone(c.consume(self.frame(step=1100,frame_id=2,translation=(.5,.04,2)),now_step=1100))
        c=consumer(max_distance_m=1)
        self.assertIsNone(c.consume(self.frame(),now_step=1000))
        self.c.invalidate()
        self.assertIsNone(self.c.current(1200))

    def test_unreadable_image_and_rgba_contract(self):
        for mode in ('missing','rgb','transparent'):
            with self.subTest(mode=mode):
                c=consumer()
                frame=self.frame()
                path=Path(frame['image_path'])
                if mode=='missing': path.unlink()
                else:
                    image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
                    if mode=='rgb': image=image[:,:,:3]
                    else: image[:,:,3]=0
                    path.write_bytes(cv2.imencode('.png',image)[1].tobytes())
                self.assertIsNone(c.consume(frame,now_step=1000))

    def test_actual_reader_envelope_without_socket_or_runtime(self):
        # Exercise the real validated file reader without binding a UDP port.
        reader=Reader.__new__(Reader)
        reader.config=copy.deepcopy(SETTINGS)
        reader.directory=Path(self.temp.name)
        reader.run_id,reader.instance_id=LIMITS['run_id'],LIMITS['instance_id']
        reader.epoch,reader.generation,reader.stream_id='a'*32,1,'b'*32
        reader.minimum_step=1000
        reader.last_step=reader.last_frame=-1
        frame=self.frame()
        result=self.c.consume(reader._read(frame['notification']),now_step=1000)
        self.assertIsNotNone(result,self.c.reason)
        with self.assertRaises(ValueError): reader._read(frame['notification'])
        malformed=self.frame(step=1100,frame_id=2)
        malformed['metadata']=None
        self.assertIsNone(self.c.consume(malformed,now_step=1100))
        self.assertIsNone(self.c.current(1100))


def evidence(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    c=consumer()
    rows=[]
    cases=[('appearance',{}),('move',dict(translation=(.15,.04,2))),
           ('occlusion',dict(occluded=True)),('recovery',dict(translation=(.4,.04,2))),
           ('loss',dict(blank=True))]
    for index,(name,kwargs) in enumerate(cases):
        step=1000+100*index
        frame=fixture(directory,step=step,frame_id=index+1,**kwargs)
        target=c.consume(frame,now_step=step)
        rows.append(dict(case=name,reason=c.reason,target=target,
                         image=Path(frame['image_path']).name,
                         image_sha256=hashlib.sha256(Path(frame['image_path']).read_bytes()).hexdigest()))
    report=dict(scope='synthetic interface test; not real RGB or flight acceptance',
                opencv=cv2.__version__,numpy=np.__version__,settings=SETTINGS,limits=LIMITS,
                expected_optical_first_m=[.12,.04,2],translation_tolerance_m=.035,cases=rows)
    (directory/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence')
    args,rest=parser.parse_known_args()
    if args.evidence:
        print(json.dumps(evidence(args.evidence),indent=2))
    else:
        unittest.main(argv=['test_aruco_consumer']+rest)
