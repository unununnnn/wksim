"""Compile actual candidate barrier source against POSIX semaphore shims; not a flight test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

CPP=r'''
#include <lockstep_scheduler/lockstep_components.h>
#include <atomic>
#include <thread>
#include <chrono>
#include <cstdio>
#include <cstdarg>
#include <sys/syscall.h>
#include <time.h>
static std::atomic<int> clocks{0};
extern "C" long __real_syscall(long,...);
extern "C" long __wrap_syscall(long n,...)
{
    if(n==SYS_clock_gettime) {
        va_list a; va_start(a,n); int id=va_arg(a,int); auto p=va_arg(a,struct timespec*); va_end(a);
        ++clocks; return __real_syscall(n,id,p);
    }
    if(n==SYS_gettid) return __real_syscall(n);
    return -1;
}
int main()
{
    LockstepComponents c;
    c.wait_for_components(); // Empty registry must never wait, including when tracing is enabled.
    int a=c.register_component(),b=c.register_component();
    if(a<=0 || b<=0 || a==b) return 2;
    std::atomic<bool> entered{false},done{false};
    std::thread t([&]{entered=true;c.wait_for_components();done=true;});
    while(!entered) std::this_thread::yield();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if(done) return 3;
    c.lockstep_progress(a);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if(done) return 4;
    c.lockstep_progress(b);
    t.join();
    c.unregister_component(a);c.unregister_component(b);
    c.wait_for_components();
    std::printf("{\"complete\":true,\"clock_reads\":%d,\"last_component\":%d}\n",int(clocks),b);
}
'''


def check(source,out):
    source,out=Path(source),Path(out);out.mkdir(parents=True,exist_ok=False)
    inc=out/'include'
    shims={'drivers/drv_hrt.h':'#pragma once\n',
      'px4_platform_common/log.h':'#pragma once\n#define PX4_DEBUG(...) ((void)0)\n#define PX4_ERR(...) ((void)0)\n',
      'px4_platform_common/tasks.h':'#pragma once\ninline const char* px4_get_taskname(){return "barrier-test";}\n',
      'px4_platform_common/sem.h':'#pragma once\n#include <semaphore.h>\nusing px4_sem_t=sem_t;\n#define px4_sem_init sem_init\n#define px4_sem_destroy sem_destroy\n#define px4_sem_wait sem_wait\n#define px4_sem_post sem_post\n#define px4_sem_getvalue sem_getvalue\n'}
    for name,data in shims.items():
        p=inc/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    (out/'test.cpp').write_text(CPP)
    lib=source/'platforms/posix/src/px4/common/lockstep_scheduler'
    command=['g++','-std=c++17','-pthread','-I'+str(inc),'-I'+str(lib/'include'),
             str(lib/'src/lockstep_components.cpp'),str(out/'test.cpp'),'-Wl,--wrap=syscall','-o',str(out/'test')]
    built=subprocess.run(command,capture_output=True,text=True)
    (out/'build.log').write_text(built.stdout+built.stderr);built.check_returncode()
    results=[]
    for label,flag in (('off',None),('on','1'),('invalid','10')):
        env=dict(os.environ);env.pop('WKSIM_PX4_COMPONENT_TIMING',None)
        if flag is not None:env['WKSIM_PX4_COMPONENT_TIMING']=flag
        r=subprocess.run([str(out/'test')],env=env,capture_output=True,text=True,timeout=3)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        r.check_returncode();data=json.loads(r.stdout)
        if label=='on':
            records=[json.loads(line.split(' ',1)[1]) for line in r.stderr.splitlines()
                     if line.startswith('WKSIM_PX4_COMPONENT ')]
            assert data['clock_reads']>0 and records
            assert records[-1]['observed_release_component']==data['last_component']
        else:assert data['clock_reads']==0 and not r.stderr
        results.append(dict(mode=label,**data))
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(status='pass',scope=__doc__,results=results,compiler_command=command,
                source_sha256=sha(lib/'src/lockstep_components.cpp'),
                header_sha256=sha(lib/'include/lockstep_scheduler/lockstep_components.h'),
                checker_sha256=sha(Path(__file__)))
    (out/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();check(a.source.resolve(),a.output.resolve())
