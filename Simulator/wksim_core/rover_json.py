"""ArduRover JSON transport adapter for the independent Ackermann model."""
import argparse
import json
from pathlib import Path
import socket
import struct
from dataclasses import asdict

from .vehicle_models import VehicleModel
from .actuator_layout import ACKERMANN,decode_layout

PACKET=struct.Struct('<HHI16H')


def serve(port,trace_path):
    model=VehicleModel('ackermann_v1');previous=None;reply=None;peer=None;time_s=0.
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock, Path(trace_path).open('x',buffering=1) as trace:
        sock.bind(('127.0.0.1',port));sock.settimeout(20)
        while time_s<180:
            packet,address=sock.recvfrom(4096)
            if address[0]!='127.0.0.1' or (peer is not None and address!=peer):
                raise ValueError('Unexpected physics peer')
            peer=address
            if len(packet)!=PACKET.size:raise ValueError('Expected AP 16-channel JSON frame')
            magic,rate,frame,*pwm=PACKET.unpack(packet)
            if magic!=18458 or not rate:raise ValueError('Invalid AP JSON frame header')
            if frame==previous:
                sock.sendto(reply,address);continue
            if previous is not None and frame!=(previous+1)%2**32:
                raise ValueError('Rover actuator frame discontinuity')
            commands=decode_layout(ACKERMANN,pwm)
            state=model.step(commands)
            time_s=state.time_s
            sensors=dict(timestamp=state.time_s,position=state.position_ned_m,
                quaternion=state.attitude_frd_to_ned_wxyz,velocity=state.velocity_ned_m_s,
                imu=dict(gyro=state.angular_velocity_frd_rad_s,accel_body=state.specific_force_frd_m_s2))
            reply=('\n'+json.dumps(sensors,separators=(',',':'),allow_nan=False)+'\n').encode()
            sock.sendto(reply,address)
            if frame%20==0:
                trace.write(json.dumps(dict(frame=frame,rate_hint=rate,actuators=commands,state=asdict(state)),allow_nan=False)+'\n')
            previous=frame


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=19002)
    parser.add_argument('--trace',type=Path,required=True)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Invalid port')
    serve(args.port,args.trace)
