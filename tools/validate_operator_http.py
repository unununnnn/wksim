"""Real operator-service acceptance, explicitly NOT browser/UI acceptance.

Uses the shipped local API and formal runtime. Never publishes DDS or overrides
FC checks. Retain all failed attempts. Own UE is closed, flights finish through
the task or its watchdog; a client exception never kills the runtime launcher.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def live_captures(view, run_id):
    """Observe original native captures; never inject or replay a state."""
    log=Path(view['readback_path']).parent/'ue.log'
    if not log.is_file():
        return []
    text=log.read_text(errors='replace')
    if 'WKSIM_READY run='+run_id+' ' not in text:
        return []
    rows=[]
    for line in text.splitlines():
        match=re.search(r'WKSIM_CAPTURE .*?(frame-\d+\.png) sequence=(-?\d+) sim=([\d.]+) stale=(\d)',line)
        if match and int(match[2])>=0 and match[4]=='0':
            frame=Path(view['frames_directory'])/match[1]
            if frame.is_file():
                rows.append(dict(path=str(frame),sha256=sha(frame),sequence=int(match[2]),sim_time_s=float(match[3])))
    return rows


ACTION_FIELDS = ('mission_id', 'action_token', 'control_epoch', 'native_generation')


def confirmed_action(api, flight, action):
    """Freeze the observed offer, re-GET, then use the shipped five-field API.

    This is a labelled validation operator, not a native publisher or browser.
    It never replaces the frozen offer with a newer token on a race or failure.
    """
    offer = flight['live']['action_offer']
    body = {key: offer[key] for key in ACTION_FIELDS}
    body['action'] = action
    latest = api('/api/runs/' + flight['id'])
    live = latest.get('live') or {}
    current = live.get('action_offer') or {}
    if (latest['id'] != flight['id'] or latest['run_id'] != flight['run_id']
            or latest.get('kind') != 'flight' or latest['status'] != 'running'
            or live.get('freshness', {}).get('status') != 'live'
            or current.get('allowed_actions') != [action]
            or any(current.get(key) != body[key] for key in ACTION_FIELDS)):
        raise ValueError('Confirmed action offer changed; no POST or automatic retry')
    response = api('/api/runs/' + flight['id'] + '/mission-action', body)
    request = response.get('request') or {}
    if (response.get('submitted') is not True or request.get('version') != 1
            or request.get('run_id') != flight['run_id']
            or any(request.get(key) != value for key, value in body.items())
            or re.fullmatch('[0-9a-f]{32}', request.get('request_id', '')) is None):
        raise ValueError('No matching submission response; outcome unknown, no retry')
    return request


def action_event(flight, request, event):
    if request is None:
        return None
    live = flight.get('live') or {}
    progress = [r.get('payload') for r in live.get('events', []) if r.get('stream') == 'mission']
    progress.append(live.get('mission'))
    for row in progress:
        if (not isinstance(row, dict) or row.get('event') != event
                or any(row.get(k) != request[k] for k in
                       ('run_id', 'mission_id', 'control_epoch', 'native_generation'))):
            continue
        key = 'pause_request' if event == 'mission_paused' else 'resume_request'
        if (row.get('pause') or {}).get(key) == request:
            return row
    return None


def audit_http_lifecycle(formal, directory, scenario, pause_request, resume_request):
    """Check formal mission history and independent physics, preserving clocks.

    Unlike the separate DDS lifecycle probe, this HTTP client adds no native
    subscriptions. It does not claim independent native-output silence proof.
    """
    assert formal['safe_landing'] and formal['children_reaped'], formal.get('error')
    task, mission = formal['task'], formal['task']['mission']
    assert len(mission['pauses']) == 1, 'Expected exactly one pause'
    pause = mission['pauses'][0]
    assert pause['pause_request'] == pause_request and pause['resume_request'] == resume_request
    assert pause_request['action_token'] != resume_request['action_token']
    assert pause['publications_after'] == pause['publications_before'], 'Task published during operator pause'
    assert pause['end_boot_s'] - pause['start_boot_s'] >= 6
    assert pause['end_truth']['final_time'] - pause['start_truth']['final_time'] >= 5.5
    start, end = pause['start_truth']['records'], pause['end_truth']['records']
    with (Path(directory) / 'truth.jsonl').open(encoding='utf-8') as source:
        window = [json.loads(line) for i, line in enumerate(source) if start <= i < end]
    assert len(window) > 10 and min(-r['vehicle'][8] for r in window) > 2.5
    envelopes = task['request_envelopes']
    assert all(a['request_id'] < b['request_id'] for a, b in zip(envelopes, envelopes[1:]))
    point = mission['waypoints'][2]
    assert point['input']['frame'] == 'body_flu' and point['attempts'][0]['status'] == 'interrupted'
    setup = next(e for e in envelopes if e['request_id'] == pause['resume_setup_request_id'])
    assert setup['setup']['control_state'] == 'COMMAND_CONTROL'
    later = [e for e in envelopes if e['request_id'] > setup['request_id']]
    if scenario == 'pause-cancel':
        assert formal['status'] == 'cancelled' and len(point['attempts']) == 1
        assert not any('command' in e and e['command']['agent_cmd'] == 4 for e in later)
        assert later[0]['command']['agent_cmd'] == 3
    else:
        assert formal['status'] == 'pass' and len(point['attempts']) == 2 and point['status'] == 'completed'
        command = later[0]['command']
        assert command['move_mode'] == 0 and command['agent_cmd'] == 4
        assert math.dist(command['position_ref'], point['target_enu_m']) < 1e-5
        assert abs(math.remainder(command['yaw_ref'] - point['yaw_enu_rad'], 2 * math.pi)) < 1e-6
        assert point['attempts'][1]['command_id'] > point['attempts'][0]['command_id']
        assert point['dwell_start_boot_s'] >= pause['end_boot_s']
        assert point['dwell_end_boot_s'] - point['dwell_start_boot_s'] >= point['dwell_s']
        assert formal['mission_truth']['ok']
    return dict(status='pass', paused_boot_s=pause['end_boot_s'] - pause['start_boot_s'],
                paused_physics_s=pause['end_truth']['final_time'] - pause['start_truth']['final_time'],
                minimum_paused_height_m=min(-r['vehicle'][8] for r in window),
                task_publications_while_paused=pause['publications_after'] - pause['publications_before'],
                native_output_silence='not independently instrumented in this HTTP test',
                attempts=len(point['attempts']), completed_waypoints=formal['mission_truth']['completed_waypoints'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--stack',choices=('px4','arducopter'),required=True)
    parser.add_argument('--case',choices=('mission','cancel','pause-resume','pause-cancel'),default='mission')
    parser.add_argument('--view',action='store_true')
    parser.add_argument('--dwell-s',type=float,help='Explicit fixed waypoint dwell; 2..10 source-clock seconds')
    parser.add_argument('--airborne-view-cycle',action='store_true',help='Require close and recovered Actor while airborne')
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args(argv)
    if not args.url.startswith('http://127.0.0.1:') or not args.url[17:].isdigit():
        parser.error('Only an explicit 127.0.0.1 service port is allowed')
    if args.dwell_s is not None and (not math.isfinite(args.dwell_s) or not 2<=args.dwell_s<=10):
        parser.error('dwell-s must be finite and in 2..10')
    if args.airborne_view_cycle and (not args.view or args.case!='mission'):
        parser.error('airborne-view-cycle requires a mission with --view')
    lifecycle = args.case in ('pause-resume', 'pause-cancel')
    if lifecycle and args.dwell_s != 10:
        parser.error('HTTP lifecycle acceptance requires explicit --dwell-s 10 for the fixed observation window')
    args.evidence.mkdir(parents=True,exist_ok=False)
    csrf=None
    result=dict(status='failed',acceptance_scope='real HTTP service/runtime, NOT browser interaction',
                stack=args.stack,case=args.case,view_requested=args.view,checks={},started_unix=time.time(),
                validator_sha256=sha(__file__),dwell_override_s=args.dwell_s,airborne_view_cycle=args.airborne_view_cycle)
    journal=(args.evidence/'http.jsonl').open('x',encoding='utf-8')
    observations=(args.evidence/'observations.jsonl').open('x',encoding='utf-8')
    flight=None

    def api(path,body=None,expect=200):
        request=Request(args.url+path,data=None if body is None else json.dumps(body,allow_nan=False).encode(),
            headers={} if body is None else {'Content-Type':'application/json','X-Wksim-CSRF':csrf or ''})
        try:
            with urlopen(request,timeout=30) as response:
                code,value=response.status,json.load(response)
        except HTTPError as error:
            code,value=error.code,json.load(error)
        # Token remains memory-only. Raw formal result is available at its path.
        record=dict(unix_s=time.time(),clock='Windows wall/unix',path=path,
                    method='GET' if body is None else 'POST',http_status=code,
                    response={k:v for k,v in value.items() if k!='csrf'})
        if path not in ('/api/bootstrap','/api/runs') and '/api/runs/' not in path or body is not None or path.endswith('/result'):
            journal.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n'); journal.flush()
        if code!=expect:
            raise RuntimeError(f'{path}: expected HTTP {expect}, got {code}: {value.get("error")}')
        return value

    def finish(ident,limit=90):
        deadline=time.monotonic()+limit
        while time.monotonic()<deadline:
            value=api('/api/runs/'+ident)
            if value['status'] not in ('queued','running'):
                return value
            time.sleep(.3)
        raise TimeoutError('Job completion deadline: '+ident)

    try:
        initial=api('/api/bootstrap'); csrf=initial['csrf']
        config=deepcopy(initial['defaults'][args.stack])
        if args.dwell_s is not None:
            for point in config['mission']['waypoints']:
                point['dwell_s']=args.dwell_s
        invalid=deepcopy(config); invalid['mission']['waypoints'][0]['position_m'][2]=0
        api('/api/preflight',dict(config=invalid),expect=400)
        result['checks']['invalid_mission_rejected_before_process']=True
        wrong=deepcopy(config); wrong['px4_root']='/opt/wksim-invalid-candidate'
        rejected=api('/api/preflight',dict(config=wrong))
        rejected=finish(rejected['id'])
        result['rejected_preflight']=rejected
        if rejected['status']!='failed':
            raise RuntimeError('Wrong candidate unexpectedly admitted')
        result['checks']['candidate_failure_visible']=bool(rejected['error'])
        name=args.stack+'-'+args.case+'-'+args.evidence.name[-12:]
        saved=api('/api/configs',dict(name=name,config=config,expected_revision=None))
        reloaded=next(c for c in api('/api/bootstrap')['configs'] if c['name']==name)
        if reloaded!=saved or saved['config']!=config:
            raise RuntimeError('Saved/reloaded configuration differs')
        result['saved']=saved
        result['checks']['save_reload_exact']=True
        check=finish(api('/api/preflight',dict(config=reloaded['config']))['id'])
        if check['status']!='pass':
            raise RuntimeError('Corrected candidate preflight rejected: '+str(check['error']))
        result['preflight']=check
        result['checks']['corrected_preflight_pass']=True
        flight=api('/api/start',dict(config=config,preflight_id=check['id'],with_view=args.view))
        result['job_id'],result['run_id'],result['directory']=flight['id'],flight['run_id'],flight['directory']
        print(json.dumps(dict(event='run_requested',status=flight['status'],job_id=flight['id'],run_id=flight['run_id']),ensure_ascii=False),flush=True)
        if flight['status'] not in ('queued','running'):
            raise RuntimeError('Flight did not start: '+str(flight['error']))
        api('/api/shutdown',{},expect=400)
        api('/api/start',dict(config=config,preflight_id=check['id'],with_view=False),expect=400)
        result['checks']['active_job_exclusion_and_shutdown_refusal']=True
        deadline=time.monotonic()+360
        seen=set(); cancel=None; view_stop=None; view_reopened=False; recovered_actor=False; recovered_airborne=False; live_sequences=[]; actor_sequences=[]
        pause_request=resume_request=pause_confirmed=resume_confirmed=None
        paused_boot=cancelled_boot=None
        old_rejected=False
        while time.monotonic()<deadline:
            flight=api('/api/runs/'+flight['id'])
            live=flight.get('live') or {}; mission=live.get('mission') or {}; raw=live.get('raw') or {}
            public=live.get('state') or {}; view=flight.get('view') or {}
            record=dict(clock='Windows wall/unix',observed_unix=time.time(),job_id=flight['id'],run_id=flight['run_id'],
                status=flight['status'],error=flight.get('error'),projection_error=flight.get('projection_error'),
                mission=mission,state=public,control=live.get('control'),freshness=live.get('freshness'),
                sequence=raw.get('sequence'),control_epoch=raw.get('control_epoch'),view=view,
                action_offer=live.get('action_offer'))
            observations.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n');observations.flush()
            phase=(flight['status'],mission.get('state'),mission.get('event'),(mission.get('waypoint') or {}).get('index'),view.get('state'))
            if phase not in seen:
                print(json.dumps(dict(event='observed',phase=phase,freshness=(live.get('freshness') or {}).get('status'))),flush=True)
                seen.add(phase)
            if (live.get('freshness') or {}).get('status')=='live':
                live_sequences.append(raw.get('sequence',0))
            actor=view.get('latest_actor') or {}
            airborne=(public.get('armed') is True and (live.get('freshness') or {}).get('status')=='live'
                      and len(public.get('position',[]))==3 and public['position'][2]>=2.5)
            if view.get('state')=='live' and actor:
                actor_sequences.append(actor['packet']['sequence'])
                if view_reopened and actor['packet']['sequence']>view_stop['last_sequence']:
                    recovered_actor=True
                    recovered_airborne |= bool(airborne and actor['packet']['position_ned_m'][2]<=-2.5)
            # Exercise closing/reopening the independent viewer while a mission runs.
            if (args.view and len(set(actor_sequences))>=5 and view_stop is None and flight['status']=='running'
                    and (not args.airborne_view_cycle or (airborne and mission.get('state')=='running'))):
                view_stop=dict(unix_s=time.time(),boot=(public.get('header') or {}).get('stamp'),
                               last_sequence=actor_sequences[-1],airborne=airborne,public_state=public,
                               frames=live_captures(view,flight['run_id']))
                api('/api/runs/'+flight['id']+'/view',dict(action='close'))
                print('Owned view closed; flight process remains untouched',flush=True)
            if view_stop and not view_reopened and time.time()-view_stop['unix_s']>=3 and flight['status']=='running':
                view_stop['after_boot']=(public.get('header') or {}).get('stamp')
                api('/api/runs/'+flight['id']+'/view',dict(action='open'));view_reopened=True
            if args.case=='cancel' and cancel is None and mission.get('state')=='running' and public.get('armed') is True and (mission.get('waypoint') or {}).get('index',0)>=1:
                cancel=api('/api/runs/'+flight['id']+'/cancel',dict(mission_id=mission['mission_id']))
                print('Formal cancel request submitted',flush=True)
            if lifecycle and flight['status']=='running':
                offer=live.get('action_offer') or {}
                point=mission.get('waypoint') or {}
                stamp=(public.get('header') or {}).get('stamp') or {}
                boot=stamp.get('sec',0)+stamp.get('nanosec',0)/1e9
                if (pause_request is None and airborne and offer.get('allowed_actions')==['pause']
                        and point.get('index')==3 and point.get('input',{}).get('frame')=='body_flu'
                        and 'dwell_start_boot_s' in point and boot-point['dwell_start_boot_s']>=.7):
                    pause_request=confirmed_action(api,flight,'pause')
                    result['pause_request']=pause_request
                    print('HTTP pause submitted; awaiting matching mission acknowledgement',flush=True)
                paused=action_event(flight,pause_request,'mission_paused')
                if paused and pause_confirmed is None:
                    pause_confirmed=paused
                    paused_boot=boot
                    result['pause_confirmed']=paused
                    stale={k:pause_request[k] for k in ACTION_FIELDS}; stale['action']='pause'
                    api('/api/runs/'+flight['id']+'/mission-action',stale,expect=400)
                    old_rejected=True
                    print('Pause confirmed and old offer rejected; observing continuing physics',flush=True)
                if (pause_confirmed and resume_request is None and mission.get('state')=='paused'
                        and offer.get('allowed_actions')==['resume'] and boot-paused_boot>=6):
                    if args.case=='pause-cancel' and cancel is None:
                        cancel=api('/api/runs/'+flight['id']+'/cancel',dict(mission_id=mission['mission_id']))
                        cancelled_boot=boot
                        print('Cancel submitted while paused; no automatic reacquisition',flush=True)
                    elif args.case=='pause-resume' or (boot-cancelled_boot>=6 and mission.get('cancel_request')==cancel['request']):
                        resume_request=confirmed_action(api,flight,'resume')
                        result['resume_request']=resume_request
                        print('HTTP explicit resume submitted; awaiting new takeover confirmation',flush=True)
                resumed=action_event(flight,resume_request,'mission_resumed')
                if resumed and resume_confirmed is None:
                    resume_confirmed=resumed
                    result['resume_confirmed']=resumed
                    print('Explicit resume confirmed by exact request identity',flush=True)
            if flight['status'] not in ('queued','running'):
                break
            time.sleep(.35)
        else:
            raise TimeoutError('Flight deadline; runtime watchdog still owns cleanup')
        result['terminal']=flight
        expected='cancelled' if args.case in ('cancel','pause-cancel') else 'pass'
        result['checks']['formal_terminal']=flight['status']==expected
        envelope=api('/api/runs/'+flight['id']+'/result')
        formal=envelope['values']
        result['result_sha256']=sha(Path(flight['directory'])/'result.json')
        result['checks']['formal_result_matches']=formal==flight['result'] and formal.get('children_reaped') is True and envelope['sha256']==result['result_sha256']
        result['checks']['advancing_public_feedback']=len(set(live_sequences))>=5
        result['cancel']=cancel
        if lifecycle:
            result['checks']['matching_pause_and_resume_feedback']=bool(pause_confirmed and resume_confirmed)
            result['checks']['old_action_offer_rejected']=old_rejected
            result['lifecycle_audit']=audit_http_lifecycle(formal,flight['directory'],args.case,pause_request,resume_request)
        first=api('/api/runs/'+flight['id']+'/evidence?stream=truth&offset=0&limit=1')
        second=api('/api/runs/'+flight['id']+'/evidence?stream=truth&offset=1&limit=1')
        result['checks']['offline_truth_pagination']=first['total']>2 and first['records']!=second['records']
        result['checks']['source_clocks_labelled']=all(r['clock']=='physics' for r in first['records']+second['records'])
        result['view_stop']=view_stop
        if args.view:
            result['checks']['actual_actor_feedback']=len(set(actor_sequences))>=5
            result['checks']['view_reopened']=view_reopened
            result['checks']['reopened_actor_advances']=recovered_actor
            result['checks']['flight_progress_without_view']=bool(view_stop and view_stop.get('after_boot')!=view_stop.get('boot'))
            result['reopened_frames']=live_captures(flight['view'],flight['run_id'])
            result['checks']['native_live_frames_both_views']=bool(view_stop and view_stop['frames'] and result['reopened_frames'])
            if args.airborne_view_cycle:
                result['checks']['closed_while_airborne']=bool(view_stop and view_stop['airborne'])
                result['checks']['reopened_actor_while_airborne']=recovered_airborne
        result['status']='pass' if all(result['checks'].values()) else 'failed'
    except Exception as error:
        result['error']=str(error)
    finally:
        if flight is not None:
            try:
                result['view_close']=api('/api/runs/'+flight['id']+'/view',dict(action='close'))
                result['last_job']=api('/api/runs/'+flight['id'])
            except Exception as error:
                result['cleanup_error']=str(error)
        result['finished_unix']=time.time()
        journal.close();observations.close()
        (args.evidence/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k in ('status','error','checks','directory','job_id','run_id')},ensure_ascii=False,indent=2),flush=True)
    return 0 if result['status']=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
