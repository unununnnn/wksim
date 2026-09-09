"""Comparator negative controls; no vehicle execution."""
import importlib.util
import json
import math
from pathlib import Path
import struct
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runner',ROOT/'tools/run_numerical_conformance.py')
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def main():
    c=r.read(r.CONTRACT); widths=c['sampling']['array_lengths']
    m=dict(case='C0',epoch='negative-controls',contract_sha256=r.CONTRACT_SHA)
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory)
        raw=(ROOT/c['cases'][0]['input']['path']).read_bytes(); (out/'input.csv').write_bytes(raw)
        inp=[[float(x) for x in row.split(',')] for row in raw.decode().splitlines()[1:]]
        (out/'applied-input.f64').write_bytes(b''.join(struct.pack('<33d',*row) for row in inp))
        for name,width in widths.items():
            (out/(name+'.f64')).write_bytes(b''.join(struct.pack('<'+'d'*(width+1),k*.001,*([0.0]*width)) for k in range(501)))
        for side in ('reference','target'): r.write(out/(side+'-process.json'),dict(exit_code=0))
        r.write(out/'reference.json',dict(status='complete',**m))
        records=[dict(schema_version=1,kind='major_recorder_start',source={},input_csv=raw.decode(),expected_calls=501,comparison_end_s=.5,expected_engine_end_s=.501)]
        for k in range(501):
            records.append(dict(schema_version=1,kind='major_recorder_sample',k=k,call_number=k+1,
                major_capture_count=1,step_status='complete',input_time_s=inp[k][1],engine_before_s=k*.001,
                engine_after_s=(k+1)*.001,inPWMs=inp[k][2:18],TerrainIn15d=inp[k][18:],
                major_root_outputs={n:[0.0]*w for n,w in widths.items()},post_step_api={n:[0.0]*w for n,w in widths.items()}))
        records.append(dict(schema_version=1,kind='major_recorder_end',status='complete',attempted_calls=501,returned_calls=501,emitted_samples=501,comparison_end_s=.5,engine_end_s=.501))
        def check():
            (out/'target.stdout.log').write_text(''.join(json.dumps(x)+'\n' for x in records))
            return r.compare(out,c,m,{'source':{}})
        assert check()['failed_values']==0
        records[1]['major_root_outputs']['Vehicle60'][0]=-0.0
        assert check()['failed_values']==0
        records[1]['major_root_outputs']['Vehicle60'][0]=math.nextafter(0.0,1.0)
        result=check(); assert result['failed_values']==1 and result['status']=='numerical_failed'
        assert len(r.read(out/'per-scalar.json'))==120
        assert len((out/'failures.jsonl').read_text().splitlines())==1
        records[1]['major_root_outputs']['Vehicle60'][0]=1
        assert check()['failed_values']==1  # JSON integer tokens still denote native binary64.
        for change in ('nonfinite','boolean','missing_end','wrong_input','clock'):
            saved=json.loads(json.dumps(records))
            if change=='nonfinite': records[1]['major_root_outputs']['Vehicle60'][0]=float('nan')
            if change=='boolean': records[1]['major_root_outputs']['Vehicle60'][0]=True
            if change=='missing_end': records.pop()
            if change=='wrong_input': records[1]['inPWMs'][0]=.1
            if change=='clock': records[1]['engine_before_s']=.001
            try: check()
            except ValueError: pass
            else: raise AssertionError(change+' should be invalid')
            records=saved
    print('PASS: exact equality, signed zero, one-ULP and integer-token failure, complete scalar/failure retention, nonfinite/boolean/missing/input/clock rejection')


if __name__=='__main__': main()
