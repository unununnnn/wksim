"""Synthetic inputs to an actual UE Hex Actor; never claim real flight evidence."""
import argparse
import copy
import json
import math
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.ue55.hex_bridge import binding, packet_from_record, display_packet, actor_readback_errors

LIMITS=dict(position_cm=2e-4,quaternion_l2=1e-6,sim_time_s=1e-8,
            origin_local_cm=1e-5,origin_world_cm=3e-4,rpm=0.,yaw_deg=1e-4,diameter_cm=1e-5,phase_deg=1e-6)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('run-id','instance-id','model-identity','output'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--port',required=True,type=int)
    args=parser.parse_args()
    expected=binding(args.run_id,args.instance_id,args.model_identity)
    directory=Path(args.output); directory.mkdir(parents=True,exist_ok=False)
    result=dict(status='failed',scope=__doc__,binding=expected,limits=LIMITS,accepted=[],rejected=[])
    (directory/'contract.json').write_text(json.dumps(result,indent=2)+'\n')
    previous=None
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as link:
        link.bind(('127.0.0.1',0));link.settimeout(2)
        destination=('127.0.0.1',args.port)
        def receive(kind,field,value):
            end=time.monotonic()+2
            while time.monotonic()<end:
                data,peer=link.recvfrom(8192)
                if peer!=destination:continue
                item=json.loads(data)
                if item.get('kind')==kind and item.get(field)==value:return item
            raise TimeoutError('Matching UE response')
        def query(index):
            request=dict(version=4,kind='hex_actor_query',**expected,request_sequence=index)
            link.sendto(json.dumps(request).encode(),destination)
            return receive('hex_actor_snapshot','request_sequence',index)
        def packet(step):
            output=[0.]*120;output[2]=step/1000
            output[6:9]=[.5,.2,-1.5]
            output[12:16]=[math.cos(.15),0.,0.,math.sin(.15)]
            output[16:22]=[100.,110.,120.,130.,140.,150.]
            now=time.monotonic_ns()
            source=packet_from_record(dict(kind='step',tick=step,observed_monotonic_ns=now,output120=output),expected,now)
            return display_packet(dict(packet=source,relay_monotonic_s=now/1e9,ended=False),expected,.001,time.time())
        try:
            for step in (1000,1100,1200):
                sent=packet(step)
                link.sendto(json.dumps(sent,allow_nan=False).encode(),destination)
                ack=receive('hex_actor','sequence',step)
                errors=actor_readback_errors(sent,ack,previous)
                for key,limit in LIMITS.items():
                    if errors.get(key) is None or errors[key]>limit:raise AssertionError((key,errors.get(key),limit))
                result['accepted'].append(dict(packet=sent,ack=ack,errors=errors));previous=ack
            before=query(1)
            base=packet(1300)
            probes=[dict(base,run_id='foreign'),dict(base,instance_id='f'*32),
                dict(base,model_identity='sha256:'+'f'*64),dict(base,rotor_rpm=[0.]*5),
                dict(base,rotor_order=list(reversed(base['rotor_order']))),dict(base,quaternion_wxyz=[0.]*4),
                dict(base,position_ned_m=[math.nan,0.,0.]),dict(base,step=True),
                dict(base,display_wall_time_s=time.time()-2),dict(base,extra=1),result['accepted'][-1]['packet']]
            fields=('sequence','step','sim_time_s','ue_position_cm','ue_quaternion_xyzw','rotors')
            for index,invalid in enumerate(probes,2):
                link.sendto(json.dumps(invalid).encode(),destination)
                time.sleep(.03)
                observed=query(index)
                assert all(observed.get(key)==before.get(key) for key in fields),index
                assert observed['rejected']==before['rejected']+index-1,index
                result['rejected'].append(dict(packet=invalid,snapshot=observed))
            time.sleep(.8)
            stale=query(100)
            assert stale['stale'] is True
            result['stale_snapshot']=stale
            # Leave enough actual rendered fresh frames for screenshot inspection.
            for index in range(1300,4300,20):
                sent=packet(index);link.sendto(json.dumps(sent).encode(),destination)
                ack=receive('hex_actor','sequence',index)
                errors=actor_readback_errors(sent,ack,previous)
                assert all(errors[k] is not None and errors[k]<=v for k,v in LIMITS.items())
                result['accepted'].append(dict(packet=sent,ack=ack,errors=errors));previous=ack
                time.sleep(.04)
            result['status']='pass'
        except Exception as error:
            result['error']=f'{type(error).__name__}: {error}'
        finally:
            from Simulator.wksim_runtime.evidence import write_json
            write_json(directory/'result.json',result)
    print(json.dumps(dict(status=result['status'],result=str(directory/'result.json'))))
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
