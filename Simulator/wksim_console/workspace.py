"""Windows-owned local jobs; all flight behavior stays in the formal WSL entry."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import threading
import time
import uuid

from Simulator.wksim_runtime.config import validate_config, _unique_object, _invalid_constant
from Simulator.wksim_runtime.mission_cancel import request_cancel
from Simulator.wksim_runtime.mission_actions import request_action
from .records import read_result

REPO = Path(__file__).resolve().parents[2]
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
IDENTIFIER = re.compile(r'[0-9a-f]{32}\Z')


def decode(text):
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def read_json(path, limit=32*1024*1024):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('Unsafe or oversized JSON file')
    return decode(path.read_text(encoding='utf-8'))


def write_json(path, value, *, replace=False):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if not replace:
        with path.open('x', encoding='utf-8') as output:
            output.write(text)
        return
    temporary = path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def revision(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def wsl_path(path):
    value = PureWindowsPath(path)
    if not value.is_absolute() or not re.fullmatch('[A-Za-z]:',value.drive):
        raise ValueError('Windows absolute drive path required')
    return '/mnt/'+value.drive[0].lower()+'/'+ '/'.join(value.parts[1:])


def tail(path, limit=16384):
    try:
        if path.is_symlink():
            raise ValueError('Symbolic log path refused')
        with path.open('rb') as source:
            size=path.stat().st_size
            source.seek(max(0,size-limit))
            return source.read(limit).decode('utf-8',errors='replace')
    except FileNotFoundError:
        return ''


class Workspace:
    def __init__(self, root, *, repo=REPO):
        raw=Path(root).absolute()
        if any(p.is_symlink() for p in (*raw.parents,raw)):
            raise ValueError('Workspace must not follow links')
        self.root, self.repo = raw, Path(repo).resolve()
        marker=raw/'.wksim-console.json'
        if raw.exists() and any(raw.iterdir()) and not marker.exists():
            raise ValueError('Refusing a nonempty directory that is not a wksim console workspace')
        raw.mkdir(parents=True,exist_ok=True)
        if not marker.exists():
            write_json(marker,dict(version=1,repo=str(self.repo)))
        elif read_json(marker) != dict(version=1,repo=str(self.repo)):
            raise ValueError('Console workspace identity mismatch')
        self.lease=(raw/'.console.lock').open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                if self.lease.tell()==0:
                    self.lease.write(b'0'); self.lease.flush()
                self.lease.seek(0)
                msvcrt.locking(self.lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise ValueError('Another console server already owns this workspace') from None
        self.config_dir, self.job_dir = raw/'configs', raw/'jobs'
        for path in (self.config_dir,self.job_dir):
            path.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.jobs, self.processes, self.logs, self.readers, self.views = {},{},{},{},{}
        self.preparing=set()
        self.stopping=threading.Event()
        self.server_instance=uuid.uuid4().hex
        source=self.repo/'Simulator/wksim_console'
        snapshot={str(p.relative_to(self.repo)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.css','.html')}
        write_json(raw/('server-'+self.server_instance+'.json'),dict(version=1,pid=os.getpid(),
            started_unix=time.time(),executable=sys.executable,python=sys.version,source_sha256=snapshot))
        for path in sorted(self.job_dir.glob('*/job.json')):
            try:
                job=read_json(path)
                if not IDENTIFIER.fullmatch(job['id']) or path.parent.name != job['id']:
                    continue
                if job['status'] in ('queued','running'):
                    job['status']='unowned'
                    job['error']='Recorded job has no current process handle; not automatically adopted or restarted'
                if job.get('view') and job['view'].get('state') not in ('stopped','failed','unavailable'):
                    job['view']=dict(job['view'],historical_state=job['view']['state'],state='unavailable',
                        latest_actor=None,error='Historical view has no current owned handle; live state cannot be verified')
                self.jobs[job['id']]=job
            except (OSError,ValueError,KeyError):
                continue
        self.worker=threading.Thread(target=self._monitor,daemon=True,name='wksim-console-observer')
        self.worker.start()

    def checked_config(self, value):
        config=validate_config(deepcopy(value))
        if 'mission' not in config or config.get('control_protocol') != 'session_v1':
            raise ValueError('The console requires an explicit session_v1 position mission; CLI legacy remains available')
        if 'display_socket' in config:
            raise ValueError('The console assigns a fresh display socket per run; remove display_socket from the saved config')
        return config

    def bootstrap(self):
        defaults={stack:read_json(self.repo/f'Simulator/wksim_runtime/examples/{stack}-mission.json')
                  for stack in ('px4','arducopter')}
        configs=[]
        for path in sorted(self.config_dir.glob('*.json')):
            try:
                value=read_json(path)
                if NAME.fullmatch(value['name']) and path.stem == value['name']:
                    configs.append(value)
            except (OSError,ValueError,KeyError):
                continue
        return dict(version=1,defaults=defaults,configs=configs,runs=self.list_runs(),data_root=str(self.root),
            ue_available=os.name=='nt' and (self.repo/'Simulator/ue55/state-build-manifest.json').is_file())

    def save_config(self,name,config,expected_revision=None):
        if not isinstance(name,str) or not NAME.fullmatch(name):
            raise ValueError('Configuration name must be 1–64 ASCII letters/digits, hyphen or underscore')
        config=self.checked_config(config)
        with self.lock:
            path=self.config_dir/(name+'.json')
            current=read_json(path)['revision'] if path.exists() else None
            if current != expected_revision:
                raise ValueError('Configuration changed or name already exists; reload before overwriting')
            record=dict(name=name,revision=revision(config),config=config)
            write_json(path,record,replace=current is not None)
            return record

    def _active(self):
        return bool(self.preparing) or any(process.poll() is None for process in self.processes.values())

    @staticmethod
    def _view_active(view):
        status=view.poll()
        return status.get('resource_held') is True or status.get('state') not in ('stopped','failed','unavailable')

    def _launch(self,argv,job,stdout_name):
        if os.name!='nt':
            raise RuntimeError('Operator host requires Windows; tests may inject the process seam')
        directory=self.job_dir/job['id']
        output=(directory/stdout_name).open('x',encoding='utf-8')
        errors=(directory/'stderr.log').open('x',encoding='utf-8')
        try:
            process=subprocess.Popen(argv,cwd=self.repo,stdout=output,stderr=errors,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            output.close(); errors.close()
            raise
        self.processes[job['id']]=process
        self.logs[job['id']]=(output,errors)
        job.update(status='running',argv=argv,pid=process.pid)

    def _new_job(self,kind,config):
        ident=uuid.uuid4().hex
        directory=self.job_dir/ident
        directory.mkdir()
        job=dict(id=ident,kind=kind,status='queued',config=config,config_revision=revision(config),
            server_instance=self.server_instance,
            run_id=None,directory=str(directory),started_unix=time.time(),finished_unix=None,error=None,
            result=None,live=None,view=None,phases=[])
        self.jobs[ident]=job
        write_json(directory/'requested-config.json',config)
        return job

    def _persist(self,job):
        # Do not copy growing raw live logs or result bodies into the job catalog.
        record={k:v for k,v in job.items() if k not in ('live','result')}
        record.update(live=None,result=None)
        write_json(self.job_dir/job['id']/'job.json',record,replace=True)

    def preflight(self,config):
        config=self.checked_config(config)
        with self.lock:
            if self._active():
                raise ValueError('Another owned check or flight is running; wait before launching another job')
            job=self._new_job('preflight',config)
            directory=self.job_dir/job['id']
            try:
                argv=['wsl.exe','-d','Ubuntu-22.04','--cd',wsl_path(self.repo),'--exec','timeout','-k','5','60',
                      'python3','-B','-m','Simulator.wksim_console.preflight_entry',wsl_path(directory/'requested-config.json')]
                self._launch(argv,job,'preflight.json')
            except Exception as error:
                job.update(status='failed',error=str(error),finished_unix=time.time())
            self._persist(job)
            return deepcopy(job)

    def start(self,config,preflight_id,with_view):
        config=self.checked_config(config)
        if type(with_view) is not bool:
            raise ValueError('with_view must be boolean')
        with self.lock:
            if self._active():
                raise ValueError('Another owned check or flight is running')
            check=self._job(preflight_id)
            if (check['kind']!='preflight' or check['status']!='pass' or
                    check['config_revision']!=revision(config)):
                raise ValueError('Run a successful preflight for the exact current configuration first')
            job=self._new_job('flight',config)
            directory=self.job_dir/job['id']
            runtime_config=deepcopy(config)
            runtime_config['run_id']=config['run_id'][:40]+'-'+uuid.uuid4().hex[:10]
            runtime_config['display_socket']='/tmp/wksim-'+runtime_config['run_id']+'/state.sock'
            job.update(run_id=runtime_config['run_id'],directory=str(directory/'runs'/runtime_config['run_id']),
                       runtime_config=runtime_config,preflight_id=preflight_id)
            write_json(directory/'runtime-config.json',runtime_config)
            try:
                from .records import LiveRunReader
                reader=LiveRunReader(Path(job['directory']),job['run_id'])
                if with_view:
                    self.preparing.add(job['id'])
                    job['preparation']=dict(state='preparing_optional_view',physics_started=False,started_unix=time.time())
                    self._open_view(job,preparing=True)
                    threading.Thread(target=self._start_after_view,args=(job,reader),daemon=True,
                                     name='wksim-view-preparation').start()
                else:
                    self._start_runtime(job,reader)
            except Exception as error:
                self.preparing.discard(job['id'])
                job.update(status='failed',error=str(error),finished_unix=time.time())
            self._persist(job)
            return deepcopy(job)

    def _start_runtime(self,job,reader):
        directory=self.job_dir/job['id']
        argv=['wsl.exe','-d','Ubuntu-22.04','--cd',wsl_path(self.repo),'--exec','bash','tools/run-wksim.sh',
              wsl_path(directory/'runtime-config.json'),'--output-root',wsl_path(directory/'runs')]
        self._launch(argv,job,'console.log')
        self.readers[job['id']]=reader

    def _start_after_view(self,job,reader):
        # Preparation happens before physics exists. Rendering never paces a
        # running experiment; a failed/closed optional viewer permits CLI mode.
        deadline=time.monotonic()+65
        try:
            while True:
                with self.lock:
                    view=self.views.get(job['id'])
                    job['view']=view.poll() if view is not None else job['view']
                    if not job['view'] or job['view']['state']!='starting':
                        break
                if time.monotonic()>deadline:
                    view.stop()
                    break
                time.sleep(.1)
            with self.lock:
                self._start_runtime(job,reader)
                job['preparation'].update(state='finished',physics_started=True,finished_unix=time.time())
        except Exception as error:
            with self.lock:
                job.update(status='failed',error=str(error),finished_unix=time.time())
        finally:
            with self.lock:
                self.preparing.discard(job['id'])
                self._persist(job)

    def _job(self,ident):
        if not isinstance(ident,str) or not IDENTIFIER.fullmatch(ident) or ident not in self.jobs:
            raise ValueError('Unknown console job identity')
        return self.jobs[ident]

    def _result_path(self,job):
        return (self.job_dir/job['id']/'preflight.json' if job['kind']=='preflight'
                else Path(job['directory'])/'result.json')

    def get_run(self,ident):
        with self.lock:
            job=self._job(ident)
            if job.get('result') is None and job['status'] in ('pass','failed','cancelled'):
                try:
                    job['result']=read_result(self._result_path(job))['values']
                except (OSError,ValueError):
                    pass
            return deepcopy(job)

    def list_runs(self):
        with self.lock:
            # History polling stays compact; selected-run GET returns live/result.
            return [deepcopy(dict(job,live=None,result=None)) for job in
                    sorted(self.jobs.values(),key=lambda j:j['started_unix'],reverse=True)]

    def cancel(self,ident,mission_id):
        with self.lock:
            job=self._job(ident)
            process=self.processes.get(ident)
            if job['kind']!='flight' or process is None or process.poll() is not None:
                raise ValueError('No live owned flight to cancel')
            request=request_cancel(Path(job['directory']),job['run_id'],mission_id)
            return dict(submitted=True,request=request)

    def mission_action(self,ident,mission_id,action_token,action,control_epoch,native_generation):
        with self.lock:
            job=self._job(ident)
            process=self.processes.get(ident)
            if (job['kind']!='flight' or job['status']!='running'
                    or job['server_instance']!=self.server_instance
                    or process is None or process.poll() is not None or ident not in self.readers):
                raise ValueError('No live owned flight for a mission action')
            # Re-poll now: catalog values alone can be stale while this lock or
            # the browser was busy. Reading state never commands the runtime.
            job['live']=self.readers[ident].poll()
            offer=job['live']['action_offer']
            if (action not in ('pause','resume') or action not in offer['allowed_actions']
                    or mission_id!=offer['mission_id'] or action_token!=offer['action_token']
                    or control_epoch!=offer['control_epoch'] or type(native_generation) is not int
                    or native_generation!=offer['native_generation']):
                raise ValueError('Mission offer is stale, unconfirmed or unavailable: '+offer['reason'])
            request=request_action(Path(job['directory']),job['run_id'],mission_id,action_token,action,
                expected_offer=dict(control_epoch=control_epoch,native_generation=native_generation))
            return dict(submitted=True,request=request)

    def _open_view(self,job,*,preparing=False):
        process=self.processes.get(job['id'])
        if job['kind']!='flight' or (not preparing and (process is None or process.poll() is not None)):
            raise ValueError('UE live view requires a running owned flight; recorded truth is not replayed to UE')
        for ident,view in self.views.items():
            if ident!=job['id'] and self._view_active(view):
                raise ValueError('Another console UE view owns the display slot')
        if job['id'] in self.views and self._view_active(self.views[job['id']]):
            return job['view']
        try:
            from .visual import View
            folder=self.job_dir/job['id']/('view-'+uuid.uuid4().hex[:8])
            folder.mkdir()
            view=View(folder,job['run_id'],job['runtime_config']['display_socket'],repo=self.repo)
            self.views[job['id']]=view
            view.start()
            job['view']=view.poll()
        except Exception as error:
            job['view']=dict(state='failed',error=str(error))
        self._persist(job)
        return job['view']

    def view(self,ident,action):
        with self.lock:
            job=self._job(ident)
            if action=='open':
                return self._open_view(job)
            if action!='close':
                raise ValueError('Unknown view action')
            owned=self.views.get(ident)
            if owned is not None:
                owned.stop()
                job['view']=owned.poll()
                self._persist(job)
            return job['view'] or dict(state='stopped')

    def evidence(self,ident,stream,offset,limit):
        with self.lock:
            job=self._job(ident)
            if job['kind']!='flight' or job['status'] not in ('pass','failed','cancelled'):
                raise ValueError('Recorded evidence requires a terminal flight')
            directory=Path(job['directory'])
        from .records import replay_page
        return replay_page(directory,stream=stream,offset=offset,limit=limit)

    def result(self,ident):
        with self.lock:
            job=self._job(ident)
            if job['status'] not in ('pass','failed','cancelled'):
                raise ValueError('Job has no terminal recorded result')
            return read_result(self._result_path(job))

    def _monitor(self):
        while not self.stopping.wait(.4):
            with self.lock:
                for ident,process in list(self.processes.items()):
                    job=self.jobs[ident]
                    try:
                        code=process.poll()
                        if code is not None and job['status']=='running':
                            for handle in self.logs.pop(ident,()):
                                handle.close()
                            try:
                                result=read_result(self._result_path(job))['values']
                                okay=(result.get('ok') is True if job['kind']=='preflight'
                                      else result.get('status') in ('pass','cancelled') and result.get('children_reaped') is True)
                                job.update(result=result,status=('pass' if job['kind']=='preflight' else result['status'])
                                           if code==0 and okay else 'failed',error=result.get('error'))
                            except (OSError,ValueError,KeyError) as error:
                                job.update(status='failed',error='Missing or invalid formal result: '+str(error))
                            if job['status']=='failed' and not job.get('error'):
                                job['error']=tail(self.job_dir/ident/'stderr.log') or 'Formal operation rejected; inspect result reasons'
                            job.update(returncode=code,finished_unix=time.time())
                            self._persist(job)
                        job['phases']=tail(self.job_dir/ident/('console.log' if job['kind']=='flight' else 'stderr.log')).splitlines()[-40:]
                        if ident in self.readers and (code is None or (job.get('live') or {}).get('freshness',{}).get('status')!='recorded'):
                            job['live']=self.readers[ident].poll(terminal=code is not None)
                        if ident in self.views:
                            job['view']=self.views[ident].poll()
                    except Exception as error:
                        # Projection failures never stop or pace the autonomous runtime.
                        job['projection_error']=str(error)

    def close(self):
        with self.lock:
            if self._active():
                raise ValueError('Cannot shut down while an owned flight/check is live; cancel and wait for its actual result')
            if any(self._view_active(v) for v in self.views.values()):
                raise ValueError('Close the owned UE view before shutting down the console')
            self.stopping.set()
        self.worker.join(timeout=2)
        self.lease.close()
