"""Recompute effective airborne LQR/MPC outputs from sealed native traces."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from validate_predictive_rate import box_qp


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_fault(physical):
    declaration=physical['actuator_disturbance']
    event_path=Path(declaration['event_path']);event=json.loads(event_path.read_text())
    if sha(event_path)!=declaration['event_sha256'] or event!=declaration['event']:
        raise ValueError('Published actuator disturbance changed')
    active=0;next_tick=0;ended=False
    with Path(declaration['input_trace']).open() as stream:
        for line in stream:
            if ended:raise ValueError('Actuator trace continues after its terminal receipt')
            row=json.loads(line)
            if row['kind']=='end':
                if row['ticks']!=next_tick or row['applied_ticks']!=active or row['event_sha256']!=declaration['event_sha256']:
                    raise ValueError('Actuator terminal receipt differs')
                ended=True;continue
            if row['kind']!='step' or row['tick']!=next_tick:raise ValueError('Actuator interval trace has gaps')
            expected_active=event['start_tick']<=next_tick<event['end_tick']
            expected=list(row['original'])
            if expected_active:
                expected[0]*=.97;active+=1
                if row['original'][0]<=.05:raise ValueError('Disturbance did not affect an active motor')
            if row['active'] is not expected_active or row['applied']!=expected:
                raise ValueError('Disturbance affected the wrong interval/channel/value')
            next_tick+=1
    if not ended or active!=1000:raise ValueError('Incomplete 1000-tick actuator disturbance')
    return dict(applied_ticks=active,trace_ticks=next_tick,event_sha256=declaration['event_sha256'],
                input_trace_sha256=sha(declaration['input_trace']))


def audit(path):
    result=json.loads(path.read_text())
    if result['status']!='pass':raise ValueError('Comparison did not pass')
    candidate_path=path.parent/'candidate.json'
    if sha(candidate_path)!=result['candidate_sha256']:raise ValueError('Copied firmware receipt changed')
    candidate=json.loads(candidate_path.read_text())
    definition_path=Path(candidate['candidate_root'])/'inputs/Simulator/firmware/rate_control'/candidate.get('design_file','quad-x-design.json')
    if sha(definition_path)!=candidate['design_sha256']:raise ValueError('Control design changed')
    definition=json.loads(definition_path.read_text())
    report=dict(status='pass',comparison_sha256=sha(path),design_sha256=sha(definition_path),
                auditor_sha256=sha(__file__),reference_solver_sha256=sha(box_qp.__code__.co_filename),runs=[])
    models=set()
    for run in result['runs']:
        physical_path=Path(run['physical_result'])
        if sha(physical_path)!=run['physical_result_sha256']:raise ValueError('Physical result changed')
        physical=json.loads(physical_path.read_text())
        fault=audit_fault(physical) if result.get('disturbance')=='motor0_command_97pct_1s' else None
        if physical['status']!='pass' or physical['fc_binary_sha256']!=candidate['binary_sha256']:
            raise ValueError('Wrong physical firmware')
        models.add(physical['model_build']['library_sha256'])
        if 'retained_model' in run and (sha(run['retained_model']['path'])!=run['retained_model']['sha256']
                or run['retained_model']['sha256']!=physical['model_build']['library_sha256']):
            raise ValueError('Retained executed physical model changed')
        if sha(run['trace'])!=run['metrics']['trace_sha256']:raise ValueError('Native trace changed')
        with Path(run['trace']).open() as source:rows=list(csv.DictReader(source))
        if not rows or int(rows[0]['armed']) or int(rows[-1]['armed']):
            raise ValueError('Native trace must bracket flight with disarmed samples')
        compared=0;maximum=0.;bounded=0
        for row in rows:
            if not (int(row['armed']) and not int(row['landed'])):continue
            algorithm=run['algorithm']
            expected_id={'native':0,'pid':1,'lqr':2,'mpc':3}[algorithm]
            if int(row['requested'])!=expected_id or int(row['effective'])!=expected_id or int(row.get('status',0))!=0:
                raise ValueError('Airborne controller fallback or mismatch')
            if algorithm not in ('lqr','mpc'):continue
            if abs(float(row['dt'])-.004)>.0002:raise ValueError('Native dt differs from predictive design')
            for axis,key in enumerate(('p','q','r')):
                design=definition['axes'][axis]
                x=np.array([float(row[key])-float(row[key+'_sp']),float(row[key+'_dot'])])
                if algorithm=='lqr':expected=float(np.clip(-np.array(design['lqr_gain'])@x,-.3,.3))
                else:
                    h=np.array(design['hessian']);f=np.array(design['linear'])@x
                    unconstrained=np.linalg.solve(h,-f)
                    expected=float(unconstrained[0] if np.max(np.abs(unconstrained))<=.3 else box_qp(h,f,.3)[0])
                actual=float(row['raw_'+('x','y','z')[axis]])
                error=abs(actual-expected);maximum=max(maximum,error);compared+=1
                bounded+=abs(actual)>.3-1e-6
                if error>1e-6:raise ValueError('Native output differs from independent controller recomputation')
        report['runs'].append(dict(algorithm=run['algorithm'],scalar_outputs_recomputed=compared,
            max_abs_error=maximum,torque_bound_scalar_samples=bounded,trace_brackets_flight=True,disturbance=fault))
    if len(models)!=1:raise ValueError('Controller comparisons used different physical model binaries')
    report['model_library_sha256']=next(iter(models))
    target=path.with_name('independent-audit.json')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report,output=str(target))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('result',type=Path)
    args=parser.parse_args();audit(args.result)
