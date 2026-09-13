"""Independent box-QP comparison for the actual C++ rate-control kernel."""
import json
import argparse
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from design_rate_control import REPO, DESTINATION, design


def box_qp(h, f, limit):
    """Primal active-set reference; independent of firmware coordinate descent."""
    n=len(f);u=np.zeros(n);active={}
    for _ in range(1000):
        gradient=h@u+f
        free=[i for i in range(n) if i not in active]
        direction=np.zeros(n)
        if free: direction[free]=np.linalg.solve(h[np.ix_(free,free)],-gradient[free])
        if np.max(np.abs(direction))<1e-10:
            violations=[(abs(gradient[i]),i) for i,side in active.items()
                        if (side<0 and gradient[i]<-1e-9) or (side>0 and gradient[i]>1e-9)]
            if not violations:return u
            del active[max(violations)[1]]
            continue
        alpha=1.;hit=None
        for i in free:
            if abs(direction[i])<1e-15:continue
            side=1 if direction[i]>0 else -1
            candidate=(side*limit-u[i])/direction[i]
            if candidate<alpha:alpha=max(0.,candidate);hit=(i,side)
        u+=alpha*direction
        if hit:
            i,side=hit;u[i]=side*limit;active[i]=side
    raise ValueError('Independent active-set QP did not converge')


CPP = r'''
#include "predictive_rate.hpp"
#include <iostream>
#include <iomanip>
int main() {
    wksim_rate::PredictiveRate controller;
    unsigned algorithm, reset; double dt, error[3], acceleration[3];
    std::cout << std::setprecision(17);
    while (std::cin >> algorithm >> reset >> dt >> error[0] >> error[1] >> error[2]
        >> acceleration[0] >> acceleration[1] >> acceleration[2]) {
        if (reset) { controller.reset(); }
        auto result = controller.update(algorithm,error,acceleration,dt);
        std::cout << result.valid << ' ' << result.sweeps << ' ' << result.residual;
        for (double value : result.torque) { std::cout << ' ' << value; }
        std::cout << '\n';
    }
}
'''


def run(family='px4'):
    out=Path(tempfile.mkdtemp(prefix='predictive-rate-',dir=REPO/'validation'))
    (out/'kernel.cpp').write_text(CPP)
    binary=out/'kernel'
    argv=['g++','-std=c++14','-O2','-Wall','-Wextra','-Werror','-I',str(DESTINATION),str(out/'kernel.cpp'),'-o',str(binary)]
    if family=='arducopter':argv.append('-DWKSIM_AP_DESIGN')
    build=subprocess.run(argv,capture_output=True,text=True,timeout=45)
    (out/'build.log').write_text(build.stdout+build.stderr)
    build.check_returncode()
    rng=np.random.default_rng(20260912)
    cases=[]
    for algorithm in (2,3):
        for i in range(1200):
            amplitude=.02 if i<400 else .5 if i<800 else 20.
            e=rng.normal(0,amplitude,3);a=rng.normal(0,amplitude*10,3)
            cases.append([algorithm,int(i%29==0),.004,*e,*a])
    cases += [[algorithm,0,dt,1,2,3,4,5,6] for algorithm,dt in ((9,.004),(2,0),(3,.02),(3,-.004))]
    text=''.join(' '.join(map(str,row))+'\n' for row in cases)
    actual=subprocess.run([str(binary)],input=text,capture_output=True,text=True,timeout=30)
    actual.check_returncode()
    output=actual.stdout.splitlines()
    if len(output)!=len(cases):raise ValueError('C++ sample count differs')
    definition=design(family);max_error=0.;max_sweeps=0
    for case,line in zip(cases,output):
        fields=list(map(float,line.split())); valid=fields[0]==1
        algorithm,_,dt,*values=case
        if algorithm not in (2,3) or abs(dt-.004)>.0002:
            if valid:raise ValueError('Invalid input produced a control output')
            continue
        if not valid:raise ValueError('Kernel did not converge for a declared test case')
        max_sweeps=max(max_sweeps,int(fields[1]))
        for axis,row in enumerate(definition['axes']):
            x=np.array([values[axis],values[axis+3]])
            expected=(float(np.clip(-np.array(row['lqr_gain'])@x,-.3,.3)) if algorithm==2 else
                float(box_qp(np.array(row['hessian']),np.array(row['linear'])@x,.3)[0]))
            error=abs(fields[3+axis]-expected);max_error=max(max_error,error)
            if error>1e-6:raise ValueError('Firmware result differs from independent QP/LQR: '+repr((case,axis,error)))
    record=dict(status='pass',family=family,cases=len(cases),scalar_comparisons=2400*3,max_abs_error=max_error,
        max_solver_sweeps=max_sweeps,build_argv=argv,
        scope='C++ kernel vs independent active-set QP and Riccati LQR; no flight evidence')
    (out/'cases.json').write_text(json.dumps(cases)+'\n')
    (out/'output.txt').write_text(actual.stdout)
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(record,output=str(out))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--family',choices=['px4','arducopter'],default='px4')
    run(parser.parse_args().family)
