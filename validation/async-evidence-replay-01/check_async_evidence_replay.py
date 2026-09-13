"""Replay one real wire log at its recorded wall cadence; verify exact output bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_runtime.evidence_stream import AsyncEvidenceStream


def check(source,output):
    source=Path(source);output=Path(output)
    output.mkdir(exist_ok=False)
    native=Path(tempfile.mkdtemp(prefix='wksim-evidence-replay-',dir='/root'))
    target=native/'wire.jsonl'
    report=dict(status='failed',scope='Lossless evidence-stream replay at recorded cadence; not a flight/rate gate',
                source=str(source),native_output=str(target),lines=0,max_write_call_ns=0,
                stream_source_sha256=hashlib.sha256((ROOT/'Simulator/wksim_runtime/evidence_stream.py').read_bytes()).hexdigest())
    first=None;began=time.monotonic();writer=AsyncEvidenceStream(target)
    try:
        with source.open(encoding='utf-8',newline='') as stream:
            for line in stream:
                stamp=json.loads(line)['issued_monotonic_s']
                if first is None:first=stamp
                due=began+stamp-first
                delay=due-time.monotonic()
                if delay>0:time.sleep(delay)
                before=time.monotonic_ns();writer.write(line)
                report['max_write_call_ns']=max(report['max_write_call_ns'],time.monotonic_ns()-before)
                report['lines']+=1
        writer.close()
        expected=hashlib.sha256(source.read_bytes()).hexdigest()
        actual=hashlib.sha256(target.read_bytes()).hexdigest()
        report.update(expected_sha256=expected,actual_sha256=actual)
        if expected!=actual or not writer.summary()['complete']:raise ValueError('Replay lost or modified evidence')
        report['status']='verified'
    except Exception as error:report['error']=repr(error)
    finally:
        try:writer.close()
        except Exception as error:report['close_error']=repr(error)
        report['writer']=writer.summary();report['elapsed_s']=time.monotonic()-began
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=check(args.source,args.output);print(json.dumps(result,indent=2))
    raise SystemExit(result['status']!='verified')
