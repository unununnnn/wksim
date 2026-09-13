"""Independent original JSON, delayed GPS source and actual UBX-write audit."""
from collections import defaultdict
from contextlib import ExitStack
import argparse
import hashlib
import json
from pathlib import Path


def require(value,reason):
    if not value:raise ValueError(reason)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root):
    with ExitStack() as streams:
        return _audit(Path(root),streams)


def _audit(root,streams):
    root=Path(root);manifest=json.loads((root/'manifest.json').read_text())
    require(manifest['failure'] is None and manifest['returncode']==0 and manifest['frames_sent']==80000,'Native run did not finish')
    for name,checksum in manifest['raw_sha256'].items():require(digest(root/name)==checksum,'Raw file changed: '+name)
    wire=streams.enter_context((root/'wire.jsonl').open())
    sent=(bytes.fromhex(row['hex']).strip() for row in (json.loads(line) for line in wire)
          if row['direction']=='send')
    samples={};warmups=set();warmed=set();generation={};birth={};previous={};groups=defaultdict(bytearray)
    plan=None;tick_count=0;byte_counts=defaultdict(int)
    for line in streams.enter_context((root/'native.tsv').open()):
        cols=line.rstrip('\n').split('\t');kind=cols[0]
        require(kind!='FAIL','Native failure: '+line.strip())
        if kind=='JSON':
            raw=bytes.fromhex(cols[1]);require(raw==next(sent),'Wire/native JSON differs')
            value=json.loads(raw);tick_count+=1
            require(value['wksim']==f"{manifest['run_id']}:{manifest['epoch']}:1:{tick_count}",'Wrong raw run/epoch/tick')
            require(abs(value['timestamp']-tick_count/1000)<1e-10 and value['position']==[0,0,0]
                    and value['velocity']==[0,0,0] and value['quaternion']==[1,0,0,0]
                    and value['imu']==dict(gyro=[0,0,0],accel_body=[0,0,-9.80665]),'Ground truth relabelled')
            require(value.get('gnss_plan')==('50000:65000' if tick_count>=45000 else None),'Plan appeared at wrong boundary')
        elif kind=='PLAN':
            require(plan is None and list(map(int,cols[1:]))==[45000,50000,65000],'Plan was late or repeated')
            plan=(50000,65000)
        elif kind=='GENERATION':
            tick,instance,number=map(int,cols[1:4])
            require(instance in (0,1) and number==generation.get(instance,0)+1,'Sensor generation was reused')
            generation[instance]=number;birth[instance]=tick;previous[instance]=-1
        elif kind=='SAMPLE':
            tick,instance,source,hal=map(int,cols[1:5]);number=int(cols[-1])
            require(instance==0,'Disabled second GPS generated data')
            require(number==generation[instance] and hal==(tick-1)*1000,'Wrong native generation/HAL phase')
            require(source>previous[instance],'Repeated or regressed native source')
            if source:require(birth[instance]<=source<=tick and tick-source<=500,'Old generation, stale or future GPS source')
            previous[instance]=source;samples[tick,instance]=(source,number)
        elif kind=='WARMUP':
            tick,instance=map(int,cols[1:3]);key=(instance,generation[instance])
            require(key not in warmed and samples[tick,instance][0]==0,'Repeated warmup or nonzero warmup source')
            warmed.add(key);warmups.add((tick,instance))
        elif kind=='WRITE':
            tick,instance,suppressed,result=map(int,cols[1:5]);raw=bytes.fromhex(cols[5]);number=int(cols[6])
            require((tick,instance) in samples and (tick,instance) not in warmups
                    and number==samples[tick,instance][1],'Write lacks a fresh same-generation sample')
            loss=50000<=tick<65000
            require(suppressed==int(loss) and result==(0 if loss else len(raw)),'Outage write or short native write')
            groups[tick,instance].extend(raw)
            byte_counts['suppressed' if loss else 'before' if tick<50000 else 'after']+=len(raw)
    require(tick_count==80000 and next(sent,None) is None and plan==(50000,65000),'Missing complete long run/plan')
    require(set(groups)==set(samples)-warmups,'Missing serial group')
    count=0
    for key,raw in groups.items():
        offset=0
        while offset<len(raw):
            require(raw[offset:offset+2]==b'\xb5\x62','Missing UBX sync')
            size=int.from_bytes(raw[offset+4:offset+6],'little');packet=raw[offset:offset+size+8]
            require(len(packet)==size+8,'Truncated UBX packet')
            a=b=0
            for v in packet[2:-2]:a=(a+v)&255;b=(b+a)&255
            require(packet[-2:]==bytes([a,b]),'Corrupt UBX checksum')
            offset+=len(packet);count+=1
    require(all(byte_counts[k]>0 for k in ('before','suppressed','after')),'Missing outage/recovery evidence')
    require((50000,0) in groups and (65000,0) in groups,'Outage endpoint samples missing')
    return dict(status='pass',scope='scheduled native AP sensor ground probe; no flight acceptance',
        ticks=tick_count,plan=plan,samples=len(samples),generations=generation,ubx_packets_including_suppressed=count,
        byte_counts=dict(byte_counts),manifest_sha256=digest(root/'manifest.json'),audit_sha256=digest(__file__))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'Use a fresh audit output')
    try:result=audit(args.root)
    except Exception as error:result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['status']=='pass' else 1)
