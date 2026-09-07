function validate_cancel(port, output)
% One real base-MATLAB cancellation through the public product bridge.
c = WksimClient(port);
guard = onCleanup(@() c.close()); %#ok<NASGU>
report = struct('ok', false, 'version', version, 'pid', feature('getpid'), ...
    'license', license('test','MATLAB'), 'session_id', c.SessionId, 'bridge_instance', c.BridgeInstance);
report.responses = {};
try
    defaults = call('configs', struct(), '');
    mission = defaults.defaults.px4.mission;
    for k=1:numel(mission.waypoints), mission.waypoints(k).dwell_s=10; end
    saved = call('config.save',struct('name','matlab-cancel','stack','px4','run_id','matlab-cancel', ...
        'mission',mission,'expected_revision',''),'');
    selector=struct('name','matlab-cancel','revision',saved.revision);
    check=call('preflight',selector,''); deadline=tic;
    while true
        job=call('status',struct('job_id',check.id),'');
        if ~any(strcmp(job.status,{'queued','running'})), break; end
        assert(toc(deadline)<90,'Preflight timeout'); pause(.5);
    end
    assert(strcmp(job.status,'pass'),'Preflight failed');
    selector.preflight_id=check.id;
    flight=call('start',selector,'');
    report.job_id=flight.id; report.run_id=flight.run_id; saveReport(); deadline=tic;
    while true
        job=call('status',struct('job_id',flight.id),flight.run_id);
        assert(strcmp(job.status,'running'),'Flight ended before cancel');
        if isstruct(job.live) && isstruct(job.live.state) && job.live.state.armed && ...
                job.live.state.position(3)>2.5 && strcmp(job.live.freshness.status,'live'), break; end
        assert(toc(deadline)<180,'Airborne timeout'); pause(.25);
    end
    report.before_cancel=job;
    report.cancel=call('cancel',struct('job_id',flight.id,'mission_id',job.live.mission.mission_id),flight.run_id);
    assert(report.cancel.submitted); saveReport(); deadline=tic;
    while true
        job=call('status',struct('job_id',flight.id),flight.run_id);
        if ~any(strcmp(job.status,{'queued','running'})), break; end
        assert(toc(deadline)<180,'Cancellation timeout'); pause(.25);
    end
    assert(strcmp(job.status,'cancelled'),'Task did not end cancelled');
    report.result=call('result',struct('job_id',flight.id),flight.run_id);
    assert(report.result.values.safe_landing && report.result.values.children_reaped);
    report.ok=true; saveReport();
catch failure
    report.error=getReport(failure,'extended','hyperlinks','off');saveReport();rethrow(failure);
end
    function value=call(method,params,runId)
        response=c.request(method,params,runId);
        report.responses{end+1}=struct('method',method,'params',params,'response',response);
        assert(response.ok,'Product rejected: %s',jsonencode(response));value=response.result;
    end
    function saveReport()
        file=fopen(output,'w','n','UTF-8');assert(file~=-1);
        fprintf(file,'%s\n',jsonencode(report));fclose(file);
    end
end
