"""Local-only operator HTTP host. Run on Windows with python -m this.module."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .workspace import Workspace, REPO, decode

MAX_BODY = 64 * 1024
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.css': ('app.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8')}


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Expected JSON fields: ' + ', '.join(sorted(expected)))
    return value


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, workspace, port=8765):
        self.workspace, self.csrf = workspace, secrets.token_urlsafe(32)
        self.audit_lock = threading.Lock()
        super().__init__(('127.0.0.1', port), Handler)
        self.authority = '127.0.0.1:' + str(self.server_port)
        self.origin = 'http://' + self.authority

    def audit(self, method, path, status, result=None):
        # HTTP acceptance is not native ACK or flight completion. Never log CSRF.
        event = dict(version=1, clock='Windows wall/unix', unix_s=time.time(),
                     method=method, path=path, http_status=status)
        if isinstance(result, dict):
            for key in ('id', 'run_id', 'config_revision', 'revision', 'submitted', 'error'):
                if key in result:
                    event[key] = result[key]
            if result.get('submitted') is True and isinstance(result.get('request'), dict):
                event['request']={key:result['request'][key] for key in
                    ('run_id','mission_id','control_epoch','native_generation','action_token','request_id','action')
                    if key in result['request']}
        with self.audit_lock:
            with (self.workspace.root/'http-actions.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n')


class Handler(BaseHTTPRequestHandler):
    server_version = 'wksim-console/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_args):
        pass

    def _reply(self, code, value, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(code)
        for key, value in {
            'Content-Type': content_type, 'Content-Length': str(len(body)),
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'Cross-Origin-Resource-Policy': 'same-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            'Connection': 'close',
        }.items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def _boundary(self):
        if self.headers.get_all('Host') != [self.server.authority]:
            raise PermissionError('Only the exact local console Host is accepted')
        origin = self.headers.get('Origin')
        if origin is not None and origin != self.server.origin:
            raise PermissionError('Cross-origin requests are refused')
        if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
            raise PermissionError('Cross-site requests are refused')

    def _body(self):
        if not secrets.compare_digest(self.headers.get('X-Wksim-CSRF', ''), self.server.csrf):
            raise PermissionError('A current local console CSRF token is required')
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Content-Type must be application/json')
        sizes = self.headers.get_all('Content-Length') or []
        if self.headers.get('Transfer-Encoding') or len(sizes) != 1 or not sizes[0].isdigit():
            raise ValueError('A single Content-Length is required; transfer encoding is refused')
        size = int(sizes[0])
        if not 0 < size <= MAX_BODY:
            raise ValueError('JSON body must be 1–65536 bytes')
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise ValueError('Incomplete JSON request')
        return decode(raw.decode('utf-8'))

    def _dispatch(self, method):
        status, value, stopping = 200, None, False
        try:
            self._boundary()
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise ValueError('Only local relative endpoints are accepted')
            path, workspace = parsed.path, self.server.workspace
            if method == 'GET' and path in STATIC and not parsed.query:
                name, content_type = STATIC[path]
                return self._reply(200, (workspace.repo/'Simulator/wksim_console/web'/name).read_bytes(), content_type)
            parts = path.split('/')
            run_endpoint = len(parts) in (4, 5) and parts[:3] == ['', 'api', 'runs']
            if parsed.query and not (method == 'GET' and run_endpoint and parts[-1] == 'evidence'):
                raise ValueError('Unexpected query parameters')
            if method == 'GET':
                if path == '/api/bootstrap':
                    value = dict(workspace.bootstrap(), csrf=self.server.csrf)
                elif path == '/api/runs':
                    value = dict(runs=workspace.list_runs())
                elif run_endpoint:
                    ident = parts[3]
                    if len(parts) == 4:
                        value = workspace.get_run(ident)
                    elif parts[4] == 'result':
                        value = workspace.result(ident)
                    elif parts[4] == 'evidence':
                        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                        if set(query) - {'stream', 'offset', 'limit'} or any(len(v) != 1 for v in query.values()):
                            raise ValueError('Unexpected or duplicate evidence query field')
                        value = workspace.evidence(ident, query.get('stream', ['prometheus'])[0],
                            int(query.get('offset', ['0'])[0]), int(query.get('limit', ['50'])[0]))
                    else:
                        raise FileNotFoundError('Unknown endpoint')
                else:
                    raise FileNotFoundError('Unknown endpoint')
            elif method == 'POST':
                body = self._body()
                if path == '/api/configs':
                    fields(body, ('name', 'config', 'expected_revision'))
                    value = workspace.save_config(**body)
                elif path == '/api/preflight':
                    fields(body, ('config',))
                    value = workspace.preflight(**body)
                elif path == '/api/start':
                    fields(body, ('config', 'preflight_id', 'with_view'))
                    value = workspace.start(**body)
                elif run_endpoint and len(parts) == 5 and parts[4] == 'cancel':
                    fields(body, ('mission_id',))
                    value = workspace.cancel(parts[3], body['mission_id'])
                elif run_endpoint and len(parts) == 5 and parts[4] == 'mission-action':
                    fields(body, ('mission_id','action_token','action','control_epoch','native_generation'))
                    value = workspace.mission_action(parts[3], **body)
                elif run_endpoint and len(parts) == 5 and parts[4] == 'view':
                    fields(body, ('action',))
                    value = workspace.view(parts[3], body['action'])
                elif path == '/api/shutdown':
                    fields(body, ())
                    workspace.close()
                    value, stopping = dict(stopping=True), True
                else:
                    raise FileNotFoundError('Unknown endpoint')
            else:
                status, value = 405, dict(error='Method not supported')
        except PermissionError as error:
            status, value = 403, dict(error=str(error))
        except FileNotFoundError as error:
            status, value = 404, dict(error=str(error))
        except (ValueError, TypeError, UnicodeError, RecursionError, TimeoutError) as error:
            status, value = 400, dict(error=str(error))
        except Exception as error:
            status, value = 500, dict(error=type(error).__name__+': '+str(error))
        try:
            if method == 'POST' or status != 200 or self.path.endswith('/result') or '/evidence?' in self.path:
                self.server.audit(method, self.path, status, value)
            self._reply(status, value)
        finally:
            if stopping:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def do_OPTIONS(self):
        self._dispatch('OPTIONS')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-root', type=Path, default=REPO/'work/operator-console')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('port must be 0..65535')
    workspace = Workspace(args.data_root)
    try:
        server = ConsoleServer(workspace, args.port)
    except Exception:
        workspace.close()
        raise
    with server:
        print(server.origin, flush=True)
        while True:
            try:
                server.serve_forever(poll_interval=.2)
                break
            except KeyboardInterrupt:
                try:
                    workspace.close()
                except ValueError as error:
                    print(str(error), flush=True)
                else:
                    break
    workspace.close()


if __name__ == '__main__':
    main()
