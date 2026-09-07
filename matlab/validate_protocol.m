function validate_protocol(port, output)
% Real MATLAB + real HTTP console, protocol/config only. No SITL/UE launch.
report = struct('version', version, 'release', version('-release'), ...
    'matlab_license_test', license('test', 'MATLAB'), 'computer', computer, ...
    'scope', 'TCP protocol and real console configuration; no flight test', 'checks', {{}});
c = WksimClient(port);
cleanup = onCleanup(@() c.close()); %#ok<NASGU>
report.bridge_instance = c.BridgeInstance;
report.session_id = c.SessionId;
r = c.request('configs', struct()); assert(r.ok);
defaults = r.result.defaults.px4;
p = struct('name', 'matlab-real', 'stack', 'px4', 'run_id', 'matlab-real', ...
    'mission', defaults.mission, 'expected_revision', '');
r = c.request('config.save', p); assert(r.ok, jsonencode(r));
report.config_revision = r.result.revision;
report.checks{end+1} = 'real console config.save accepted';
r = c.request('runs', struct()); assert(r.ok && isempty(r.result.runs));
report.checks{end+1} = 'no simulation jobs started';
r = c.request('step', struct()); assert(~r.ok && strcmp(r.error.code, 'unknown_method'));
p.model_library = '/tmp/unauthorized.so';
r = c.request('config.save', p); assert(~r.ok && strcmp(r.error.code, 'invalid_params'));
report.checks{end+1} = 'unknown method and runtime path injection rejected';
old = c.SessionId; c.close();
c = WksimClient(port); assert(~strcmp(old, c.SessionId));
report.checks{end+1} = 'explicit reconnect creates new session without replay';
c.close();
% Fragment/coalescence and invalid wire inputs through an actual tcpclient.
s = tcpclient('127.0.0.1', port, 'Timeout', 5);
hello = '{"version":1,"request_id":"raw1","session_id":null,"run_id":null,"method":"hello","params":{}}';
bytes = unicode2native(hello, 'UTF-8');
write(s, bytes(1:17), 'uint8'); pause(.02); write(s, [bytes(18:end) 10], 'uint8');
h = readjson(s); assert(h.ok);
req = @(id, session) sprintf('{"version":1,"request_id":"%s","session_id":"%s","run_id":null,"method":"runs","params":{}}\n', id, session);
write(s, unicode2native([req('raw2', h.session_id) req('raw3', h.session_id)], 'UTF-8'), 'uint8');
a = readjson(s); b = readjson(s); assert(a.ok && b.ok);
write(s, unicode2native(req('raw2', h.session_id), 'UTF-8'), 'uint8');
r = readjson(s); assert(~r.ok && strcmp(r.error.code, 'duplicate_request'));
write(s, unicode2native(req('raw4', old), 'UTF-8'), 'uint8');
r = readjson(s); assert(~r.ok && strcmp(r.error.code, 'stale_session'));
bad = {'{bad}', '{"x":NaN}', '{"x":1e999}', '{"x":1,"x":2}'};
for i = 1:numel(bad)
    write(s, unicode2native([bad{i} newline], 'UTF-8'), 'uint8');
    r = readjson(s); assert(~r.ok);
end
write(s, [uint8(255) 10], 'uint8'); r = readjson(s); assert(~r.ok);
write(s, [repmat(uint8('x'), 1, 65537) 10], 'uint8');
r = readjson(s); assert(~r.ok && strcmp(r.error.code, 'frame_too_large'));
clear s;
report.checks{end+1} = 'fragment/coalescence, duplicate request, stale session, JSON/nonfinite/UTF8/oversize rejection';
report.ok = true;
f = fopen(output, 'w', 'n', 'UTF-8'); assert(f ~= -1);
guard = onCleanup(@() fclose(f)); %#ok<NASGU>
fprintf(f, '%s\n', jsonencode(report));
disp(jsonencode(report));
end

function value = readjson(s)
data = uint8([]); deadline = tic;
while true
    assert(toc(deadline) < 6, 'Response timeout');
    if s.NumBytesAvailable == 0, pause(.01); continue; end
    byte = read(s, 1, 'uint8');
    if byte == 10, break; end
    data(end+1) = byte; %#ok<AGROW>
    assert(numel(data) <= 1048576);
end
value = jsondecode(native2unicode(data, 'UTF-8'));
end
