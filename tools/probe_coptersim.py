"""Bounded, loopback-only observation of the installed CopterSim NoUI model mode.

Does not send actuator/flight commands, start a flight controller, or test licensing.
The CLI order follows https://rflysim.com/doc/zh/3.Soft/coptersim.html .
"""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import selectors
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=Path('E:/rflysimtools/CopterSim/CopterSimNoUI.exe'))
    parser.add_argument('--seconds', type=int, choices=range(1, 31), default=6)
    options = parser.parse_args()
    exe = options.exe.resolve(strict=True)
    result_dir = Path(__file__).resolve().parents[1] / 'validation' / datetime.datetime.now().strftime('coptersim-%Y%m%d-%H%M%S-%f')
    result_dir.mkdir(parents=True)
    ports = (30101, 20010, 20101)
    sockets = []
    child = None
    counts = collections.Counter()
    samples = {}
    result = {
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'executable': str(exe), 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
        'scope': 'NoUI model-only launch and passive UDP observation; not SITL flight or DDS verification',
    }
    command = [str(exe), '1', '1', '0', '0', '3', 'Grasslands', '127.0.0.1', '0', '0', '0', '0', 'Mavlink_Full']
    result['command'] = command
    try:
        with selectors.DefaultSelector() as selector, (result_dir / 'stdout.log').open('wb') as stdout, (result_dir / 'stderr.log').open('wb') as stderr:
            # Refuse occupied ports; never share sockets with another simulation.
            for port in ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(('127.0.0.1', port))
                sock.setblocking(False)
                selector.register(sock, selectors.EVENT_READ, port)
            child = subprocess.Popen(command, cwd=exe.parent, stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            result['pid'] = child.pid
            deadline = time.monotonic() + options.seconds
            while time.monotonic() < deadline and child.poll() is None:
                for key, _ in selector.select(timeout=min(0.2, max(0, deadline-time.monotonic()))):
                    data, address = key.fileobj.recvfrom(65535)
                    counts[str(key.data)] += 1
                    samples.setdefault(str(key.data), {'bytes': len(data), 'source': address, 'prefix_hex': data[:24].hex()})
            result['alive_at_deadline'] = child.poll() is None
            result['exit_before_cleanup'] = child.poll()
    except (OSError, ValueError) as error:
        result['error'] = str(error)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        for sock in sockets:
            sock.close()
        result['packets'] = dict(counts)
        result['first_packets'] = samples
        result['child_stopped'] = child is None or child.poll() is not None
        result['result_dir'] = str(result_dir)
        (result_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('alive_at_deadline') and counts and 'error' not in result else 1


if __name__ == '__main__':
    raise SystemExit(main())
