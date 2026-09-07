"""Bounded UTF-8 JSON lines over localhost TCP, forwarding the public console API."""
import argparse
from copy import deepcopy
import http.client
import json
import math
import re
import socket
import socketserver
import threading
import time
import uuid
from urllib.parse import urlencode

from Simulator.wksim_console.workspace import decode, revision
from Simulator.wksim_runtime.config import validate_config

MAX_FRAME = 65536
MAX_RESPONSE = 1024 * 1024
MAX_REQUESTS = 4096
METHODS = ('hello', 'configs', 'config.save', 'preflight', 'start', 'runs',
           'status', 'result', 'logs', 'cancel', 'mission.action')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
JOB = re.compile(r'[0-9a-f]{32}\Z')


class Rejected(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise Rejected('invalid_params', 'Expected exactly: ' + names)


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise Rejected('invalid_json', 'Nonfinite JSON number')
    if isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)


class Console:
    def __init__(self, port, timeout=5):
        self.port, self.timeout = port, timeout
        initial = self.call('GET', '/api/bootstrap')
        self.csrf = initial['csrf']
        # Local operator-controlled runtime paths are pinned at bridge startup.
        self.defaults = initial['defaults']

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=self.timeout)
        try:
            headers = {}
            raw = None
            if body is not None:
                raw = json.dumps(body, allow_nan=False).encode('utf-8')
                headers = {'Content-Type': 'application/json', 'X-Wksim-CSRF': self.csrf}
            conn.request(method, path, body=raw, headers=headers)
            response = conn.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise Rejected('response_too_large', 'Use a smaller log page; response exceeds 1 MiB')
            value = decode(raw.decode('utf-8'))
            finite(value)
            if response.status != 200:
                raise Rejected('product_rejected', str(value.get('error', response.status)))
            return value
        except (OSError, http.client.HTTPException) as error:
            raise Rejected('outcome_unknown', 'Upstream unavailable or timed out; do not retry writes automatically') from error
        finally:
            conn.close()

    def config(self, name, expected):
        values = self.call('GET', '/api/bootstrap')['configs']
        matches = [row for row in values if row['name'] == name and row['revision'] == expected]
        if len(matches) != 1:
            raise Rejected('stale_config', 'Reload configurations and use the current revision')
        value = matches[0]['config']
        stack = value.get('stack')
        if stack not in self.defaults:
            raise Rejected('invalid_params', 'Only px4 and arducopter independent missions are supported')
        allowed = validate_config(dict(deepcopy(self.defaults[stack]), run_id=value['run_id'], mission=value['mission']))
        if value != allowed or revision(value) != expected:
            raise Rejected('invalid_params', 'Configuration changes pinned runtime fields; use config.save')
        return value

    def dispatch(self, method, p, run_id):
        if method in ('configs', 'runs'):
            fields(p, '')
            if method == 'runs':
                return self.call('GET', '/api/runs')
            configs = self.call('GET', '/api/bootstrap')['configs']
            return dict(configs=[dict(name=c['name'], revision=c['revision'], stack=c['config']['stack'],
                                     run_id=c['config']['run_id'], mission=c['config'].get('mission')) for c in configs],
                        defaults={s: dict(run_id=c['run_id'], mission=c['mission']) for s, c in self.defaults.items()})
        if method == 'config.save':
            fields(p, 'name stack run_id mission expected_revision')
            if not isinstance(p['stack'], str) or p['stack'] not in self.defaults:
                raise Rejected('invalid_params', 'Unsupported stack')
            if not isinstance(p['expected_revision'], str) or (p['expected_revision'] and
                    re.fullmatch('[0-9a-f]{64}', p['expected_revision']) is None):
                raise Rejected('invalid_params', 'expected_revision must be empty for creation or a SHA256 revision')
            config = validate_config(dict(deepcopy(self.defaults[p['stack']]), run_id=p['run_id'], mission=p['mission']))
            return self.call('POST', '/api/configs', dict(name=p['name'], config=config, expected_revision=p['expected_revision'] or None))
        if method in ('preflight', 'start'):
            fields(p, 'name revision' if method == 'preflight' else 'name revision preflight_id')
            config = self.config(p['name'], p['revision'])
            body = dict(config=config)
            if method == 'start':
                body.update(preflight_id=p['preflight_id'], with_view=False)
            return self.call('POST', '/api/' + method, body)
        params = {'status': 'job_id', 'result': 'job_id', 'logs': 'job_id stream offset limit',
                  'cancel': 'job_id mission_id',
                  'mission.action': 'job_id mission_id action_token action control_epoch native_generation'}
        if method not in params:
            raise Rejected('unknown_method', 'Unsupported method; raw commands, step, shell and files are not exposed')
        fields(p, params[method])
        if not isinstance(p['job_id'], str) or not JOB.fullmatch(p['job_id']):
            raise Rejected('invalid_params', 'Invalid console job_id')
        path = '/api/runs/' + p['job_id']
        job = self.call('GET', path)
        if run_id != job.get('run_id'):
            raise Rejected('stale_run', 'run_id does not match the console job')
        if method == 'status':
            return job
        if method == 'result':
            return self.call('GET', path + '/result')
        if method == 'logs':
            if (p['stream'] not in ('prometheus', 'dds', 'truth', 'telemetry') or
                    type(p['offset']) is not int or not 0 <= p['offset'] <= 10000000 or
                    type(p['limit']) is not int or not 1 <= p['limit'] <= 100):
                raise Rejected('invalid_params', 'Invalid stream, offset (0..10000000), or limit (1..100)')
            return self.call('GET', path + '/evidence?' + urlencode({k: p[k] for k in ('stream', 'offset', 'limit')}))
        if not isinstance(run_id, str) or not ID.fullmatch(run_id):
            raise Rejected('stale_run', 'A live flight run_id is required')
        if method == 'mission.action' and p['action'] not in ('pause', 'resume'):
            raise Rejected('unsupported_command', 'Only offered pause/resume mission actions are supported')
        if method == 'mission.action' and (type(p['native_generation']) is not int or
                not 0 <= p['native_generation'] <= 2**53-1):
            raise Rejected('invalid_params', 'native_generation must be an exact MATLAB-safe nonnegative integer')
        return self.call('POST', path + ('/cancel' if method == 'cancel' else '/mission-action'),
                         {k: v for k, v in p.items() if k != 'job_id'})


class Bridge(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, console, port=8766, timeout=10):
        self.console, self.timeout, self.instance = console, timeout, uuid.uuid4().hex
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', port), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(socketserver.StreamRequestHandler):
    def frame(self):
        deadline = time.monotonic() + self.server.timeout
        while b'\n' not in self.pending:
            if len(self.pending) > MAX_FRAME:
                return bytes(self.pending)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout()
            self.connection.settimeout(remaining)
            chunk = self.connection.recv(min(4096, MAX_FRAME + 2 - len(self.pending)))
            if not chunk:
                return bytes(self.pending)
            self.pending.extend(chunk)
        end = self.pending.index(10) + 1
        raw = bytes(self.pending[:end])
        del self.pending[:end]
        self.connection.settimeout(self.server.timeout)
        return raw

    def handle(self):
        self.connection.settimeout(self.server.timeout)
        self.pending = bytearray()
        session, seen = None, set()
        for _ in range(MAX_REQUESTS):
            request_id = run_id = None
            close = False
            try:
                raw = self.frame()
                if not raw:
                    return
                if len(raw) > MAX_FRAME + 1 or not raw.endswith(b'\n'):
                    close = True
                    raise Rejected('frame_too_large', 'Frame must end in LF and contain at most 65536 bytes before LF')
                request = decode(raw[:-1].decode('utf-8'))
                finite(request)
                fields(request, 'version request_id session_id run_id method params')
                request_id, run_id = request['request_id'], request['run_id']
                if (type(request['version']) is not int or request['version'] != 1 or
                        not isinstance(request_id, str) or not ID.fullmatch(request_id) or
                        not (run_id is None or isinstance(run_id, str) and ID.fullmatch(run_id)) or
                        not isinstance(request['method'], str)):
                    request_id = run_id = None
                    raise Rejected('invalid_request', 'Invalid protocol version or identity')
                if request_id in seen:
                    raise Rejected('duplicate_request', 'Request ID was already consumed; no replay')
                seen.add(request_id)
                method = request['method']
                if method == 'hello':
                    fields(request['params'], '')
                    if session is not None or request['session_id'] is not None or run_id is not None:
                        raise Rejected('stale_session', 'hello requires a fresh connection and null identities')
                    session = uuid.uuid4().hex
                    value = dict(methods=METHODS, max_frame_bytes=MAX_FRAME, max_response_bytes=MAX_RESPONSE,
                                 idle_timeout_s=self.server.timeout, max_requests=MAX_REQUESTS,
                                 semantics='Write acceptance is not native ACK or physical completion; never auto-retry')
                else:
                    if session is None or request['session_id'] != session:
                        raise Rejected('stale_session', 'Connect with hello; old connection requests are never replayed')
                    if method in ('configs', 'config.save', 'preflight', 'start', 'runs') and run_id is not None:
                        raise Rejected('invalid_request', 'This method requires null run_id')
                    value = self.server.console.dispatch(method, request['params'], run_id)
                response = dict(ok=True, result=value)
            except socket.timeout:
                return
            except (Rejected, ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as error:
                response = dict(ok=False, error=dict(code=getattr(error, 'code', 'invalid_request'), message=str(error)[:512]))
            except (OSError, http.client.HTTPException):
                return
            response.update(version=1, bridge_instance=self.server.instance, session_id=session,
                            request_id=request_id, run_id=run_id, observed_unix_s=time.time())
            try:
                wire = json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8')
                if len(wire) > MAX_RESPONSE:
                    response.pop('result', None)
                    response.update(ok=False, error=dict(code='response_too_large', message='Response exceeds 1 MiB; narrow the request'))
                    wire = json.dumps(response).encode('utf-8')
                self.wfile.write(wire + b'\n')
            except (OSError, ValueError):
                return
            if close:
                return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--console-port', type=int, default=8765)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.console_port <= 65535 or not 0 <= args.port <= 65535:
        parser.error('Invalid TCP port')
    with Bridge(Console(args.console_port), args.port) as server:
        print(json.dumps(dict(host='127.0.0.1', port=server.server_address[1], bridge_instance=server.instance)), flush=True)
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
