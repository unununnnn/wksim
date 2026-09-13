"""Explicit contained QGC bridge; transports original bytes, generates no commands."""
import argparse
import base64
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time

from Simulator.wksim_runtime.gcs_relay import MAX_FRAME, MAX_BATCH, MAX_AGE, frame_bytes

REPO = Path(__file__).resolve().parents[2]
MAX_RESPONSE = MAX_BATCH * (MAX_FRAME * 2) + 4096


def wsl_path(path):
    value = str(Path(path).resolve()).replace('\\', '/')
    if not value[1:3] == ':/':
        raise ValueError('Repository must be on a Windows drive')
    return '/mnt/' + value[0].lower() + value[2:]


class PipeExchange:
    """One outstanding request, with main-thread deadlines even if a pipe stalls."""
    def __init__(self, child):
        self.child = child
        self.requests, self.replies = queue.Queue(1), queue.Queue(1)
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def _read(self):
        raw = self.child.stdout.readline(MAX_RESPONSE + 1)
        if not raw or len(raw) > MAX_RESPONSE or not raw.endswith(b'\n'):
            raise ConnectionError('Invalid or closed WSL relay output')
        return json.loads(raw)

    def _work(self):
        try:
            self.replies.put(self._read())
            while True:
                request = self.requests.get()
                self.child.stdin.write(json.dumps(request, separators=(',', ':'), allow_nan=False).encode() + b'\n')
                self.child.stdin.flush()
                self.replies.put(self._read())
                if request == {'stop': True}:
                    return
        except BaseException as error:
            self.replies.put(error)

    def receive(self, timeout=3):
        try:
            result = self.replies.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError('WSL GCS relay transaction exceeded deadline') from None
        if isinstance(result, BaseException):
            raise result
        return result

    def exchange(self, request):
        self.requests.put_nowait(request)
        return self.receive()


def bridge(repo, forward_socket, reverse_socket, qgc_endpoint, *, relay_port=14570,
           readback=None, stop_file=None, duration=None):
    if not isinstance(qgc_endpoint, str) or ':' not in qgc_endpoint:
        raise ValueError('QGC endpoint must be 127.0.0.1:<port>')
    host, port = qgc_endpoint.rsplit(':', 1)
    if host != '127.0.0.1' or not 10000 <= int(port) <= 60999:
        raise ValueError('QGC endpoint must be loopback 10000-60999')
    qgc = ('127.0.0.1', int(port))
    if type(relay_port) is not int or not 10000 <= relay_port <= 60999 or relay_port == int(port):
        raise ValueError('Relay port must be 10000-60999 and distinct from QGC')
    argv = ['wsl.exe', '-d', 'Ubuntu-22.04', '--cd', wsl_path(repo), '--exec',
            'python3', '-B', '-m', 'Simulator.wksim_runtime.gcs_relay',
            '--forward-socket', forward_socket, '--reverse-socket', reverse_socket]
    counters = dict(forwarded=0, reverse=0, invalid=0, dropped=0)
    child = pump = None
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, \
            (Path(readback).open('x', encoding='utf-8', buffering=1) if readback else nullcontext()) as evidence:
        def record(kind, **fields):
            if evidence:
                evidence.write(json.dumps(dict(kind=kind, unix_s=time.time(), **fields)) + '\n')
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        udp.bind(('127.0.0.1', relay_port))
        udp.connect(qgc)  # OS filters unexpected source endpoints; replies use one owned port.
        udp.setblocking(False)
        try:
            child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            pump = PipeExchange(child)
            ready = pump.receive(timeout=15)
            if ready.get('ready') is not True:
                raise ConnectionError('Relay did not confirm readiness')
            record('gcs_bridge_start', qgc=list(qgc), relay_port=relay_port, argv=argv,
                   windows_pid=child.pid, linux=ready)
            sequence = 0
            while not ((stop_file and Path(stop_file).exists()) or
                       (duration is not None and time.monotonic() - started >= duration)):
                if child.poll() is not None:
                    raise ConnectionError('WSL GCS relay exited: ' + str(child.returncode))
                reverse = None
                try:
                    packet = udp.recv(MAX_FRAME + 1)
                    reverse = base64.b64encode(packet).decode('ascii')
                    frame_bytes(reverse)
                except (BlockingIOError, ConnectionResetError):
                    reverse = None
                except ValueError:
                    counters['invalid'] += 1
                    reverse = None
                sequence += 1
                requested = time.monotonic()
                reply = pump.exchange(dict(sequence=sequence, created_unix_s=time.time(), reverse=reverse))
                if reply.get('sequence') != sequence or not isinstance(reply.get('frames'), list) or len(reply['frames']) > MAX_BATCH:
                    raise ValueError('Invalid relay response identity/bounds')
                if reverse is not None:
                    counters['reverse'] += 1
                    record('gcs_bridge_reverse', packet_base64=reverse, relay=reply['counters'])
                if time.monotonic() - requested > MAX_AGE:
                    counters['dropped'] += len(reply['frames'])
                    raise TimeoutError('GCS transport stalled; close the socket to discard all queued commands')
                for encoded in reply['frames']:
                    packet = frame_bytes(encoded)
                    try:
                        udp.send(packet)
                        counters['forwarded'] += 1
                        record('gcs_bridge_forward', packet_base64=encoded,
                               sha256=hashlib.sha256(packet).hexdigest())
                    except OSError:
                        counters['dropped'] += 1
                time.sleep(.005)
            stopped = pump.exchange({'stop': True})
            if stopped.get('stopped') is not True:
                raise ConnectionError('Relay did not confirm owned cleanup')
            child.wait(timeout=5)
            record('gcs_bridge_stop', counters=counters, relay=stopped, returncode=child.returncode)
            if child.returncode != 0:
                raise ConnectionError('Relay failed during shutdown')
            return counters
        finally:
            if child is not None:
                if child.poll() is None:
                    # Only the Popen created here. Linux relay also exits on pipe EOF;
                    # abnormal termination is recorded, never claimed as clean reaping.
                    child.terminate()
                    child.wait(timeout=5)
                    record('gcs_bridge_aborted', returncode=child.returncode, counters=counters)
                if pump is None or not pump.thread.is_alive():
                    if child.stdin: child.stdin.close()
                    if child.stdout: child.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=REPO)
    parser.add_argument('--forward-socket', required=True)
    parser.add_argument('--reverse-socket', required=True)
    parser.add_argument('--qgc-endpoint', required=True)
    parser.add_argument('--relay-port', type=int, default=14570)
    parser.add_argument('--readback')
    parser.add_argument('--stop-file')
    parser.add_argument('--duration', type=float)
    args = parser.parse_args()
    bridge(args.repo, args.forward_socket, args.reverse_socket, args.qgc_endpoint,
           relay_port=args.relay_port, readback=args.readback, stop_file=args.stop_file, duration=args.duration)


if __name__ == '__main__':
    main()

