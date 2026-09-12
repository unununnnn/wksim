function probe_reference_first_step(model_dir, input_csv, out_dir, opts)
%PROBE_REFERENCE_FIRST_STEP First-step (k=0->1) reference-side observability probe.
%
%  probe_reference_first_step(model_dir, input_csv, out_dir)
%    model_dir : folder with Exp1_MinModelTemp.slx and Exp1_MinModelTemp_init.m.
%                Read-only; nothing here is saved.
%    input_csv : the frozen C3G input.csv (501x33). Read-only.
%    out_dir   : NEW folder for the JSON report; the report file refuses to
%                overwrite any existing file.
%
%  Reuses the frozen R1 reference setup (model, init, C3G input, ode4, fixed 1 ms)
%  from export_model_reference.m but runs ONLY k=0->1 (StopTime = 0.001 s) and, in
%  normal mode, registers documented execution-event listeners on the rigid-body
%  6DOF continuous-state integrators to record the ACTUAL event order, the
%  simulation time, and the accessible block I/O and continuous states (native
%  dtype / shape / full-precision hex).
%
%  This never assumes exactly four solver stages per step and never treats an
%  integrator input as automatically a valid derivative (limit/reset config is
%  recorded). If a quantity is not accessible it is reported 'unavailable' with a
%  reason; the run never fabricates a passing empty trace. The model's original
%  StartFcn/InitFcn are preserved (read, chained, restored), temporary callbacks
%  and listeners are cleaned up, and the model is closed without saving.
%
%  This is a diagnostic entry only; it is not a numerical-acceptance run and does
%  not change the frozen R1 contract, budgets, or gates.

if nargin < 3
    error('wk:probe:args', 'usage: probe_reference_first_step(model_dir, input_csv, out_dir[, opts])');
end
if nargin < 4
    opts = struct();
end
if ~isfield(opts, 'probe_pqr_input')
    opts.probe_pqr_input = false;   % default off: the verified four-integrator mode is unchanged
end
if ~islogical(opts.probe_pqr_input) || ~isscalar(opts.probe_pqr_input)
    error('wk:probe:opts', 'opts.probe_pqr_input must be a scalar logical');
end
model = 'Exp1_MinModelTemp';
report_file = fullfile(out_dir, 'reference-first-step.json');

% Atomically reserve a new directory before loading or changing any model.
reservation = java.io.File(out_dir);
if ~reservation.mkdir()
    error('wk:probe:overwrite', 'output directory must be new: %s', out_dir);
end
assert(strcmp(version, '9.13.0.2049777 (R2022b)'), 'wk:probe:version', 'frozen R2022b required');
assert(~bdIsLoaded(model), 'wk:probe:loaded', 'probe requires its own fresh model session');
assert(strcmp(local_sha256(input_csv), '721c88bf3f621923b98bb43251c50bae7817106a984be64345c0528d34d3adcf'), ...
    'wk:probe:inputhash', 'C3G input bytes differ');
assert(strcmp(local_sha256(fullfile(model_dir, [model '.slx'])), ...
    'c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392'), 'wk:probe:modelhash', 'model bytes differ');
assert(strcmp(local_sha256(fullfile(model_dir, [model '_init.m'])), ...
    '9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991'), 'wk:probe:inithash', 'init bytes differ');
for name = {'wk_probe_log','wk_probe_listeners','wk_probe_regok','wk_probe_register','wk_probe_input','wk_probe_dropped','wk_probe_log2','wk_probe_dropped2','wk_probe_pqr_target'}
    assert(evalin('base', sprintf('exist(''%s'',''var'')', name{1})) == 0, ...
        'wk:probe:workspace', 'probe workspace name already in use');
end
old_path = path;
old_generation = Simulink.fileGenControl('getConfig');
environment_cleanup = onCleanup(@() local_environment_cleanup(old_path, old_generation)); %#ok<NASGU>
restoredefaultpath; addpath(model_dir); addpath(fileparts(mfilename('fullpath')));
Simulink.fileGenControl('set', 'CacheFolder', fullfile(out_dir,'cache'), ...
    'CodeGenFolder', fullfile(out_dir,'codegen'), 'createDir', true);

report = struct('status', 'unavailable', 'reason', 'not run', 'case', 'C3G', ...
    'model', model, 'solver', 'ode4', 'fixed_step_s', 0.001, 'stop_time_s', 0.001, ...
    'note', 'first-step reference observability probe; not a numerical acceptance run');

load_system(fullfile(model_dir, [model '.slx']));
orig_start = get_param(model, 'StartFcn');
orig_init = get_param(model, 'InitFcn');
% Shared store lives in the base workspace (where sim/StartFcn evaluate).
assignin('base', 'wk_probe_log', {});
assignin('base', 'wk_probe_listeners', {});
assignin('base', 'wk_probe_regok', {});
assignin('base', 'wk_probe_dropped', 0);
assignin('base', 'wk_probe_log2', {});
assignin('base', 'wk_probe_dropped2', 0);
assignin('base', 'wk_probe_pqr_target', []);
cleanup = onCleanup(@() local_cleanup(model, orig_start, orig_init));  %#ok<NASGU>

try
    % ---- reuse frozen init + C3G input + solver/1ms (mirrors export_model_reference.m) ----
    evalin('base', sprintf('run(''%s'')', strrep(fullfile(model_dir, [model '_init.m']), '''', '''''')));
    a = readmatrix(input_csv, 'NumHeaderLines', 1);
    assert(isequal(size(a), [501 33]) && all(isfinite(a(:))), 'wk:probe:input', 'input.csv must be 501x33 finite');
    assert(isequal(a(:,1), (0:500)') && all(abs(a(:,2) - (0:500)' * .001) <= 1e-12), 'wk:probe:inputgrid', 'input grid mismatch');
    inp = Simulink.SimulationData.Dataset;
    inp = inp.addElement(timeseries(a(:, 3:18), a(:, 2)), 'inPWMs');
    inp = inp.addElement(timeseries(a(:, 19:33), a(:, 2)), 'TerrainIn15d');
    assignin('base', 'wk_probe_input', inp);
    set_param(model, 'SimulationMode', 'normal', 'Solver', 'ode4', 'FixedStep', '0.001', ...
        'StartTime', '0', 'StopTime', '0.001', 'LoadExternalInput', 'on', ...
        'ExternalInput', 'wk_probe_input', 'SaveTime', 'on', 'TimeSaveName', 'wk_probe_tout', ...
        'SaveOutput', 'on', 'OutputSaveName', 'wk_probe_yout', 'ReturnWorkspaceOutputs', 'on', ...
        'SaveFormat', 'Dataset', 'LimitDataPoints', 'off', 'Decimation', '1');
    for name = {'inPWMs', 'TerrainIn15d'}
        set_param([model '/' name{1}], 'SampleTime', '0.001', 'Interpolate', 'off');
    end

    % ---- discover the rigid-body 6DOF continuous-state integrators at run time ----
    % Library links are resolved in the loaded model; full paths through the link are
    % discovered here (not assumed from offline structure). Names are whitespace-normalized.
    all_integ = find_system(model, 'FollowLinks', 'on', 'LookUnderMasks', 'all', 'BlockType', 'Integrator');
    state_names = {'ub,vb,wb', 'p,q,r', 'q0 q1 q2 q3', 'xe,ye,ze'};
    targets = {};
    for i = 1:numel(all_integ)
        bn = strtrim(strrep(get_param(all_integ{i}, 'Name'), sprintf('\n'), ' '));
        if any(strcmp(bn, state_names))
            targets{end+1} = all_integ{i};  %#ok<AGROW>
        end
    end
    report.all_integrator_paths = all_integ;
    report.state_integrator_paths = targets;
    if isempty(targets)
        report.status = 'unavailable';
        report.reason = ['no rigid-body 6DOF integrator blocks resolved through the ' ...
            'library link in the loaded model (see all_integrator_paths); cannot observe states'];
        local_write_report(report_file, report);
        return;
    end

    % ---- record each integrator's limit/reset config (input is not automatically a valid derivative) ----
    integ_meta = {};
    for i = 1:numel(targets)
        p = targets{i};
        m = struct('path', p, 'name', strtrim(strrep(get_param(p, 'Name'), sprintf('\n'), ' ')), ...
            'sid', get_param(p, 'SID'));
        for f = {'LimitOutput', 'UpperSaturationLimit', 'LowerSaturationLimit', ...
                 'ExternalReset', 'InitialConditionSource', 'InitialCondition'}
            try
                m.(f{1}) = get_param(p, f{1});
            catch
                m.(f{1}) = 'unavailable';
            end
        end
        integ_meta{end+1} = m;  %#ok<AGROW>
    end
    report.integrator_config = integ_meta;

    % ---- optional (default off): trace the p,q,r integrator's real upstream solver input ----
    pqr_probe = struct('enabled', false);
    pqr_target = [];
    if opts.probe_pqr_input
        pqr_probe = struct('enabled', true, 'status', 'unavailable', ...
            'reason', 'not traced', 'upstream', [], 'pqr_integrator', '', ...
            'note', ['port count/order are read from the RuntimeObject at capture, ' ...
                'never assumed; the R1 mrdivide expectation (a 3-element numerator vector, ' ...
                'a 9-element (3x3) inertia matrix, a 3-element result vector) is an ' ...
                'element-count reference, not a port count and not a gate']);
        pqr_path = '';
        for i = 1:numel(targets)
            bn = strtrim(strrep(get_param(targets{i}, 'Name'), sprintf('\n'), ' '));
            if strcmp(bn, 'p,q,r')
                pqr_path = targets{i};
            end
        end
        if isempty(pqr_path)
            pqr_probe.reason = 'p,q,r integrator not among the resolved state integrators';
        else
            resolved = resolve_probe_solver_input(pqr_path);
            pqr_probe.status = resolved.status;
            pqr_probe.reason = resolved.reason;
            pqr_probe.hops = resolved.hops;
            pqr_probe.upstream = resolved.upstream;
            pqr_probe.pqr_integrator = pqr_path;
            if strcmp(resolved.status, 'traced')
                pqr_target = resolved.target_path;
                assignin('base', 'wk_probe_pqr_target', pqr_target);
            end
        end
    end
    report.pqr_input_probe = pqr_probe;

    % ---- register execution-event listeners via a chained StartFcn (original preserved) ----
    % Function handles to local functions are stored in the base workspace; invoking the
    % stored handle from the StartFcn (base workspace) preserves the closure. Each event is
    % bound by name in a closure so no EventData property is assumed.
    assignin('base', 'wk_probe_register', @() local_register(targets, pqr_target));
    reg_call = 'wk_probe_register();';
    if ischar(orig_start) && ~isempty(strtrim(orig_start))
        temp_start = sprintf('%s\n%s', orig_start, reg_call);  % run original, then register
    else
        temp_start = reg_call;  % model has no string StartFcn to chain (this model's is empty)
    end
    set_param(model, 'StartFcn', temp_start);

    % ---- run k=0->1 only ----
    actual = sim(model);
    report.major_times = actual.wk_probe_tout;
    report.major_outputs = struct;
    dataset = actual.wk_probe_yout;
    names = {'Sensor30','GPS30','Vehicle60'};
    for port = 1:3
        channel = dataset.get(port);
        ts = channel.Values;
        samples = cell(numel(ts.Time),1);
        for k = 1:numel(ts.Time)
            samples{k} = local_native(getdatasamples(ts,k));
        end
        report.major_outputs.(names{port}) = struct('times',ts.Time,'samples',{samples});
    end

    % ---- assemble report from whatever actually fired (no stage count assumed) ----
    log = evalin('base', 'wk_probe_log');
    report.listener_registration = evalin('base', 'wk_probe_regok');
    report.events = log;
    report.event_count = numel(log);
    report.dropped_events = evalin('base', 'wk_probe_dropped');
    report.ode4_stage_mapping = 'unverified; event order alone is not a solver-stage proof';
    deriv_events = sum(cellfun(@(r) isfield(r, 'event') && strcmp(r.event, 'PostDerivatives'), log));
    report.post_derivatives_events = deriv_events;
    if opts.probe_pqr_input
        log2 = evalin('base', 'wk_probe_log2');
        report.pqr_input_probe.events = log2;
        report.pqr_input_probe.event_count = numel(log2);
        report.pqr_input_probe.dropped_events = evalin('base', 'wk_probe_dropped2');
        if report.pqr_input_probe.event_count == 0 && strcmp(pqr_probe.status, 'traced')
            report.pqr_input_probe.status = 'partial';
            report.pqr_input_probe.reason = 'upstream traced but its PostOutputs listener captured no events';
        end
    end
    if report.event_count == 0
        report.status = 'unavailable';
        report.reason = 'no execution events captured; execution listeners did not fire on the integrator blocks';
    elseif deriv_events == 0
        report.status = 'partial';
        report.reason = 'events captured but no Derivatives-method events; stage-level derivatives not observable';
    else
        report.status = 'partial';
        report.reason = sprintf('captured %d events including %d PostDerivatives; numeric accessibility and stage mapping require inspection', ...
            report.event_count, deriv_events);
    end
    local_write_report(report_file, report);
catch ex
    report.status = 'error';
    report.reason = ex.message;
    try
        local_write_report(report_file, report);
    catch
    end
    rethrow(ex);
end
end

function local_register(targets, extra_target)
%LOCAL_REGISTER Attach Pre/Post Derivatives/Outputs listeners to each integrator,
%   plus one PostOutputs listener on the traced p,q,r upstream block when given.
%   Runs in the base workspace via the model StartFcn while the simulation is running.
%   A block that cannot take a listener (e.g. removed/virtual) is recorded, not fatal.
events = {'PreDerivatives', 'PostDerivatives', 'PreOutputs', 'PostOutputs'};
handles = evalin('base', 'wk_probe_listeners');
regok = evalin('base', 'wk_probe_regok');
for i = 1:numel(targets)
    for j = 1:numel(events)
        ev = events{j};
        try
            h = add_exec_event_listener(targets{i}, ev, @(rto, evt) local_capture(rto, ev));
            handles{end+1} = h;  %#ok<AGROW>
            regok{end+1} = struct('block', targets{i}, 'event', ev, 'status', 'registered');  %#ok<AGROW>
        catch ME
            regok{end+1} = struct('block', targets{i}, 'event', ev, 'status', ['failed: ' ME.message]);  %#ok<AGROW>
        end
    end
end
if ~isempty(extra_target)
    try
        h = add_exec_event_listener(extra_target, 'PostOutputs', @(rto, evt) local_capture_pqr(rto));
        handles{end+1} = h;  %#ok<AGROW>
        regok{end+1} = struct('block', getfullname(extra_target), 'event', 'PostOutputs', 'status', 'registered');  %#ok<AGROW>
    catch ME
        regok{end+1} = struct('block', 'pqr-upstream', 'event', 'PostOutputs', 'status', ['failed: ' ME.message]);  %#ok<AGROW>
    end
end
assignin('base', 'wk_probe_listeners', handles);
assignin('base', 'wk_probe_regok', regok);
end

function local_capture(rto, event_name)
%LOCAL_CAPTURE Record one execution event from the block runtime object (read-only).
log = evalin('base', 'wk_probe_log');
if numel(log) >= 10000
    assignin('base', 'wk_probe_dropped', evalin('base','wk_probe_dropped') + 1);
    return;
end
rec = struct('event', event_name);
try, rec.time = rto.CurrentTime; catch, rec.time = 'unavailable'; end
try, rec.block = getfullname(rto.BlockHandle); catch, rec.block = 'unavailable'; end
try, rec.num_cont_states = rto.NumContStates; catch, rec.num_cont_states = 'unavailable'; end
try
    st = rto.SampleTimes;
    rec.sample_times = local_native(st);
catch
    rec.sample_times = 'unavailable';
end
try
    cs = rto.ContStates();
    rec.cont_states = local_native(cs);
catch ME
    rec.cont_states = ['unavailable: ' ME.message];
end
try
    dv = rto.Derivatives();
    rec.derivatives = local_native(dv);
catch ME
    rec.derivatives = ['unavailable: ' ME.message];
end
try
    rec.input1 = local_native(rto.InputPort(1).Data);
catch ME
    rec.input1 = ['unavailable: ' ME.message];
end
try
    rec.output1 = local_native(rto.OutputPort(1).Data);
catch ME
    rec.output1 = ['unavailable: ' ME.message];
end
log{end+1} = rec;
assignin('base', 'wk_probe_log', log);
end

function local_capture_pqr(rto)
%LOCAL_CAPTURE_PQR Record one PostOutputs event from the traced upstream block.
%   Same discipline as local_capture: read-only, capped, and every port count
%   comes from the RuntimeObject at capture time.
log = evalin('base', 'wk_probe_log2');
if numel(log) >= 10000
    assignin('base', 'wk_probe_dropped2', evalin('base','wk_probe_dropped2') + 1);
    return;
end
rec = struct('event', 'PostOutputs');
try, rec.time = rto.CurrentTime; catch, rec.time = 'unavailable'; end
try, rec.block = getfullname(rto.BlockHandle); catch, rec.block = 'unavailable'; end
rec.order = numel(log) + 1;   % sequence position is the real callback order
try
    % InputPort/OutputPort are RunTimeBlock METHODS, not arrays: numel(rto.InputPort)
    % would be numel of a method handle (1), not a port count. Use the documented
    % NumInputPorts/NumOutputPorts and index the methods.
    n_in = rto.NumInputPorts;
    rec.input_port_count = n_in;
    inputs = cell(n_in, 1);
    for port = 1:n_in
        try
            inputs{port} = local_native(rto.InputPort(port).Data);
        catch ME
            inputs{port} = ['unavailable: ' ME.message];
        end
    end
    rec.inputs = inputs;
catch ME
    rec.input_port_count = 'unavailable';
    rec.inputs = ['unavailable: ' ME.message];
end
try
    % Capture ALL actual output ports, not only OutputPort(1).
    n_out = rto.NumOutputPorts;
    rec.output_port_count = n_out;
    outputs = cell(n_out, 1);
    for port = 1:n_out
        try
            outputs{port} = local_native(rto.OutputPort(port).Data);
        catch ME
            outputs{port} = ['unavailable: ' ME.message];
        end
    end
    rec.outputs = outputs;
catch ME
    rec.output_port_count = 'unavailable';
    rec.outputs = ['unavailable: ' ME.message];
end
log{end+1} = rec;
assignin('base', 'wk_probe_log2', log);
end

function s = local_native(x)
%LOCAL_NATIVE Native dtype / shape / full-precision hex of a numeric value.
wrapper = '';
% Simulink's UDD data handles need not satisfy isobject/isprop. Probe the
% documented Data property directly and preserve failure information.
if ~isnumeric(x) && ~ischar(x)
    wrapper = class(x);
    try
        x = x.Data;
    catch ME
        s = struct('status','unavailable','runtime_data_object',wrapper,'reason',ME.message);
        try, s.available_properties = properties(x); catch, end
        return;
    end
end
if ~isnumeric(x)
    s = ['not numeric: ' class(x)];
    return;
end
s = struct('dtype', class(x), 'shape', size(x), 'runtime_data_object', wrapper);
if isa(x, 'double') || isa(x, 'single')
    flat = x(:);
    hexes = cell(numel(flat), 1);
    for k = 1:numel(flat)
        hexes{k} = num2hex(flat(k));   % documented full-precision IEEE hex
    end
    s.hex = hexes;
else
    s.value = x;
end
end

function local_write_report(report_file, report)
% CREATE_NEW binds refusal and opening to one filesystem operation.
options = javaArray('java.nio.file.OpenOption', 2);
options(1) = java.nio.file.StandardOpenOption.CREATE_NEW;
options(2) = java.nio.file.StandardOpenOption.WRITE;
target = java.io.File(report_file);
stream = java.nio.file.Files.newOutputStream(target.toPath(), options);
cleanup = onCleanup(@() stream.close()); %#ok<NASGU>
bytes = unicode2native([jsonencode(report) newline], 'UTF-8');
stream.write(typecast(uint8(bytes), 'int8'), 0, numel(bytes));
end

function value = local_sha256(filename)
fid = fopen(filename, 'rb');
assert(fid ~= -1, 'wk:probe:read', 'cannot read bound input');
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid, Inf, '*uint8');
md = java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes);
value = lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[]));
end

function local_environment_cleanup(old_path, old_generation)
Simulink.fileGenControl('setConfig', 'config', old_generation);
path(old_path);
end

function local_cleanup(model, orig_start, orig_init)
%LOCAL_CLEANUP Delete listeners, restore original callbacks, close without saving.
try
    handles = evalin('base', 'wk_probe_listeners');
    for i = 1:numel(handles)
        try, delete(handles{i}); catch, end
    end
catch
end
try
    if bdIsLoaded(model)
        set_param(model, 'StartFcn', orig_start);
        set_param(model, 'InitFcn', orig_init);
    end
catch
end
try
    evalin('base', 'clear wk_probe_log wk_probe_listeners wk_probe_regok wk_probe_register wk_probe_input wk_probe_tout wk_probe_yout wk_probe_dropped wk_probe_log2 wk_probe_dropped2 wk_probe_pqr_target');
catch
end
try
    if bdIsLoaded(model)
        close_system(model, 0);   % 0 = discard; source/model is never saved
    end
catch
end
end
