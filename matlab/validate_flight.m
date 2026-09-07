function validate_flight(port, folder, phase, stack)
% Real product acceptance. Writes are sent once; reconnect phase is read-only.
report = struct('ok', false, 'phase', phase, 'version', version, ...
    'computer', computer, 'license', license('test','MATLAB'), 'pid', feature('getpid'));
journal = fopen(fullfile(folder, [phase '-requests.jsonl']), 'w');
cleanup = onCleanup(@() fclose(journal)); %#ok<NASGU>
c = WksimClient(port);
report.session_id = c.SessionId; report.bridge_instance = c.BridgeInstance;
try
    if strcmp(phase, 'launch')
        defaults = call('configs', struct(), '');
        mission = defaults.defaults.(stack).mission;
        for k = 1:numel(mission.waypoints), mission.waypoints(k).dwell_s = 10; end
        mission.waypoints = [mission.waypoints; mission.waypoints];
        name = ['matlab-flight-' stack];
        saved = call('config.save', struct('name', name, 'stack', stack, ...
            'run_id', name, 'mission', mission, 'expected_revision', ''), '');
        selector = struct('name', name, 'revision', saved.revision);
        check = call('preflight', selector, '');
        report.preflight_id = check.id; saveReport();
        deadline = tic;
        while true
            job = call('status', struct('job_id', check.id), '');
            if ~any(strcmp(job.status, {'queued','running'})), break; end
            assert(toc(deadline)<90, 'Preflight deadline'); pause(.5);
        end
        assert(strcmp(job.status,'pass'), 'Preflight failed');
        selector.preflight_id = check.id;
        flight = call('start', selector, '');
        report.job_id = flight.id; report.run_id = flight.run_id; saveReport();
        deadline = tic;
        while true
            job = status();
            assert(strcmp(job.status,'running'), 'Flight ended before airborne pause');
            if isstruct(job.live) && isstruct(job.live.state) && ...
                    job.live.state.armed && job.live.state.position(3)>2.5 && ...
                    strcmp(job.live.freshness.status,'live') && ...
                    any(strcmp(job.live.action_offer.allowed_actions,'pause')), break; end
            assert(toc(deadline)<180, 'Airborne deadline'); pause(.25);
        end
        report.pause_submission = action(job, 'pause'); saveReport();
        waitEvent('mission_paused', report.pause_submission.request);
        pause(6);
        deadline = tic;
        while true
            job = status();
            assert(strcmp(job.status,'running'), 'Flight ended before resume offer');
            if strcmp(job.live.freshness.status,'live') && ...
                    any(strcmp(job.live.action_offer.allowed_actions,'resume')), break; end
            assert(toc(deadline)<20, 'No fresh public resume offer within 20 seconds'); pause(.25);
        end
        report.resume_submission = action(job, 'resume'); saveReport();
        waitEvent('mission_resumed', report.resume_submission.request);
        job = status();
        assert(strcmp(job.status,'running') && job.live.state.armed && job.live.state.position(3)>1);
        report.before_close = job;
    else
        prior = jsondecode(fileread(fullfile(folder, 'launch-result.json')));
        assert(~strcmp(c.SessionId,prior.session_id) && strcmp(c.BridgeInstance,prior.bridge_instance));
        report.job_id = prior.job_id; report.run_id = prior.run_id;
        job = status();
        assert(strcmp(job.status,'pass'), 'Formal flight must pass');
        report.result = call('result', struct('job_id',report.job_id), report.run_id);
        for stream = {'truth','prometheus','dds','telemetry'}
            report.logs.(stream{1}) = call('logs', struct('job_id',report.job_id, ...
                'stream',stream{1},'offset',0,'limit',3), report.run_id);
        end
        report.reconnected_status = job;
    end
    c.close(); report.closed_unix_s = posixtime(datetime('now','TimeZone','UTC'));
    report.ok = true; saveReport();
catch failure
    c.close(); report.error = getReport(failure,'extended','hyperlinks','off'); saveReport(); rethrow(failure);
end
    function value = call(method, params, runId)
        response = c.request(method,params,runId);
        fprintf(journal,'%s\n',jsonencode(struct('method',method,'params',params,'response',response)));
        assert(response.ok, 'Product rejected: %s', jsonencode(response));
        value = response.result;
    end
    function job = status()
        job = call('status',struct('job_id',report.job_id),report.run_id);
        assert(strcmp(job.id,report.job_id) && strcmp(job.run_id,report.run_id));
    end
    function value = action(job, verb)
        offer = job.live.action_offer;
        assert(any(strcmp(offer.allowed_actions,verb)));
        params = struct('job_id',report.job_id,'mission_id',offer.mission_id, ...
            'action_token',offer.action_token,'action',verb,'control_epoch',offer.control_epoch, ...
            'native_generation',offer.native_generation);
        value = call('mission.action',params,report.run_id);
        assert(value.submitted && strcmp(value.request.action_token,offer.action_token));
    end
    function waitEvent(event, request)
        deadline = tic;
        while true
            job = status();
            rows = job.live.events;
            for n = 1:numel(rows)
                if iscell(rows), row = rows{n}; else, row = rows(n); end
                payload = row.payload;
                if strcmp(row.stream,'mission') && isfield(payload,'event') && strcmp(payload.event,event)
                    assert(strcmp(payload.run_id,request.run_id) && ...
                        strcmp(payload.control_epoch,request.control_epoch) && ...
                        strcmp(payload.mission_id,request.mission_id));
                    if strcmp(event,'mission_paused'), key='pause_request'; else, key='resume_request'; end
                    assert(isequal(payload.pause.(key),request));
                    return;
                end
            end
            assert(strcmp(job.status,'running') && toc(deadline)<30, 'Action confirmation deadline'); pause(.25);
        end
    end
    function saveReport()
        file = fopen(fullfile(folder,[phase '-result.json']),'w');
        fprintf(file,'%s\n',jsonencode(report)); fclose(file);
    end
end
