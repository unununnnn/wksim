BUNDLE='/mnt/c/Users/PC/Documents/odid编译/wksim/validation/coordination/architecture-candidate-sync-20260913-02/main.bundle'
EXPECTED='386f713a7752515502fd2224e9186f2219674732'
import json,subprocess,pathlib,time
p=pathlib.Path('/root/wksim-architecture-acceptance-20260913')
def git(*args):
 r=subprocess.run(['git','-C',str(p),*args],capture_output=True,text=True);row={'argv':list(args),'exit_code':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()};log.append(row);return r
log=[]
assert git('rev-parse','HEAD').stdout.strip()=='d45d1dad81600b37fb41c945870ee455a3ee81f0'
assert git('branch','--show-current').stdout.strip()=='codex/architecture-acceptance-20260913'
assert git('status','--porcelain').stdout==''
assert git('merge-base','--is-ancestor','f333316e6efa6b299b4288a9d91fb2bccedfb9d6','HEAD').returncode==0
assert git('fetch',BUNDLE,'refs/heads/main:refs/remotes/main-coordinator/main').returncode==0
assert git('merge','--ff-only','refs/remotes/main-coordinator/main').returncode==0
assert git('rev-parse','HEAD').stdout.strip()==EXPECTED
assert git('status','--porcelain').stdout==''
assert git('merge-base','--is-ancestor','f333316e6efa6b299b4288a9d91fb2bccedfb9d6','HEAD').returncode==0
print(json.dumps({'checked_unix':time.time(),'cwd':str(p),'new_head':EXPECTED,'operations':log,'native_executed':False,'private_wiring_migrated':False,'architecture_acceptance':False}))
