"""Notification/replay rejection using protocol fixtures, not sensor evidence."""
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest

from Simulator.ue55.rgb import Reader, config


def settings(port=19172):
    return dict(version=1,vehicle_id=2,sensor_id='front_rgb',width=640,height=480,
                horizontal_fov_degrees=90,position_cm=[30,0,50],quaternion_xyzw=[0,0,0,1],
                interval_steps=100,notify_port=port)


class RgbConsumerTests(unittest.TestCase):
    def test_config_bounds(self):
        for changes in (dict(vehicle_id=True),dict(width=0),dict(height=4096,width=4096),
                        dict(sensor_id='../old'),dict(notify_port=19060),dict(interval_steps=0),
                        dict(position_cm=[float('nan'),0,0]),dict(quaternion_xyzw=[0,0,0,2]),
                        dict(horizontal_fov_degrees=float('inf')),dict(extra=1)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):config(dict(settings(),**changes))

    def test_notified_frames_only_and_retired_identity_rejected(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reader=Reader(root,'run','a'*32,settings(port))
            try:
                reader.set_epoch('b'*32,1)
                data=dict(schema='wksim.rgb.v1',run_id='run',instance_id='a'*32,epoch='b'*32,
                          vehicle_id='2',sensor_id='front_rgb',step='100',frame_id='1',sim_time_seconds=.1,
                          width=640,height=480,image='fixture.png')
                (root/'fixture.json').write_text(json.dumps(data))
                # Header fixture exercises decoder admission only, not PNG pixel validity.
                (root/'fixture.png').write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',640,480))
                self.assertEqual(reader.poll(),[])  # Existing files are never replayed.
                event=dict(schema='wksim.rgb-ready.v1',run_id='run',instance_id='a'*32,epoch='b'*32,
                           generation=1,metadata='fixture.json')
                self.assertEqual(reader._read(event)['metadata']['step'],'100')
                with self.assertRaises(ValueError):reader._read(event)
                reader.set_epoch('c'*32,2)
                with self.assertRaises(ValueError):reader._read(event)
                with self.assertRaises(ValueError):reader.set_epoch('b'*32,1)
                for changes in (dict(metadata='../fixture.json'),dict(epoch='b'*32),dict(instance_id='d'*32)):
                    candidate=dict(event,epoch='c'*32,generation=2)
                    candidate.update(changes)
                    with self.assertRaises(ValueError):reader._read(candidate)
            finally:reader.close()


if __name__=='__main__':unittest.main()
