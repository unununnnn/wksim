classdef WksimClient < handle
    % Optional base-MATLAB TCP client. No reconnect, retry, step or keepalive.
    properties (SetAccess = private)
        SessionId = ''
        BridgeInstance = ''
    end
    properties (Access = private)
        Socket
        Counter = 0
        Timeout = 7
    end
    methods
        function obj = WksimClient(port)
            if nargin < 1, port = 8766; end
            obj.Socket = tcpclient('127.0.0.1', port, 'Timeout', obj.Timeout);
            hello = obj.request('hello', struct(), '');
            if ~hello.ok
                obj.close();
                error('wksim:Handshake', '%s', hello.error.message);
            end
            obj.SessionId = hello.session_id;
            obj.BridgeInstance = hello.bridge_instance;
        end
        function response = request(obj, method, params, runId)
            % Returns explicit product/protocol errors. A transport error closes
            % this client: a write outcome may be unknown and must not be retried.
            if nargin < 4, runId = ''; end
            if isempty(obj.Socket), error('wksim:Closed', 'Client is closed'); end
            obj.Counter = obj.Counter + 1;
            id = sprintf('m%d', obj.Counter);
            session = 'null'; run = 'null';
            if ~isempty(obj.SessionId), session = jsonencode(obj.SessionId); end
            if ~isempty(runId), run = jsonencode(runId); end
            body = sprintf('{"version":1,"request_id":%s,"session_id":%s,"run_id":%s,"method":%s,"params":%s}', ...
                jsonencode(id), session, run, jsonencode(method), jsonencode(params, 'ConvertInfAndNaN', false));
            bytes = unicode2native(body, 'UTF-8');
            if numel(bytes) > 65536, error('wksim:Frame', 'Request exceeds 65536 bytes'); end
            try
                write(obj.Socket, [bytes uint8(10)], 'uint8');
                data = uint8([]); deadline = tic;
                while true
                    if toc(deadline) > obj.Timeout
                        error('wksim:Timeout', 'Outcome unknown; reconnect explicitly and inspect state, never auto-retry');
                    end
                    count = obj.Socket.NumBytesAvailable;
                    if count == 0, pause(0.01); continue; end
                    data = [data read(obj.Socket, min(count, 1048577 - numel(data)), 'uint8')]; %#ok<AGROW>
                    ending = find(data == 10, 1);
                    if ~isempty(ending)
                        if ending ~= numel(data), error('wksim:Frame', 'Unexpected extra response frame'); end
                        response = jsondecode(native2unicode(data(1:end-1), 'UTF-8'));
                        if response.version ~= 1 || ~strcmp(response.request_id, id)
                            error('wksim:Identity', 'Response request identity mismatch');
                        end
                        if ~isempty(obj.SessionId) && (~strcmp(response.session_id, obj.SessionId) || ...
                                ~strcmp(response.bridge_instance, obj.BridgeInstance))
                            error('wksim:Identity', 'Response connection identity mismatch');
                        end
                        return
                    end
                    if numel(data) >= 1048577, error('wksim:Frame', 'Response exceeds 1 MiB'); end
                end
            catch failure
                obj.close();
                rethrow(failure);
            end
        end
        function close(obj)
            obj.Socket = [];
            obj.SessionId = '';
        end
        function delete(obj)
            obj.close();
        end
    end
end
