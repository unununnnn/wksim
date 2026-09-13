"""Real cross-distro namespace/loopback fixture; no ROS or flight controller."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_runtime import netns_handoff as handoff


def receive_exact(peer, length):
    value = b""
    while len(value) < length:
        part = peer.recv(length - len(value))
        if not part:
            raise RuntimeError("echo peer closed early")
        value += part
    return value


def source_hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__).resolve(), Path(handoff.__file__).resolve())}


def save_result(directory, durable, name, report):
    data = json.dumps(report, indent=2) + "\n"
    (directory / name).write_text(data)
    with (durable / name).open("x") as output:
        output.write(data)


def owner(directory, durable):
    before = source_hashes()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(60)
        token = secrets.token_hex(16)
        identity = dict(port=listener.getsockname()[1], echo=token,
                        net=os.readlink("/proc/self/ns/net"), owner_distro=os.environ.get("WSL_DISTRO_NAME"))
        (directory / "owner.json").write_text(json.dumps(identity) + "\n")
        result = {}

        def echo():
            try:
                with listener.accept()[0] as peer:
                    peer.settimeout(5)
                    payload = token.encode("ascii")
                    assert receive_exact(peer, len(payload)) == payload
                    peer.sendall(b"ok:" + payload)
                    result["echo_pass"] = True
            except BaseException as error:
                result["echo_error"] = repr(error)

        worker = threading.Thread(target=echo)
        worker.start()
        try:
            grant = handoff.export_namespace(directory, "cross-distro-fixture", timeout=60)
            worker.join(timeout=65)
            assert not worker.is_alive() and result.get("echo_pass"), result
        finally:
            try: listener.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            worker.join(timeout=6)
    assert source_hashes() == before
    assert not (directory / "grant.json").exists() and not (directory / "namespace.sock").exists()
    report = dict(grant=grant, source_sha256=before, endpoints_removed=True, **result)
    report["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    save_result(directory, durable, "owner-result.json", report)
    print(json.dumps(report))


def client(directory, durable):
    before = source_hashes()
    deadline = time.monotonic() + 20
    while not (directory / "grant.json").is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("namespace grant readiness")
        time.sleep(0.01)
    target = json.loads((directory / "owner.json").read_text())
    origin = os.readlink("/proc/self/ns/net")
    assert origin != target["net"], "fixture must start in different networks"
    # A wrong run must fail before joining or consuming the one-use endpoint.
    try:
        handoff.enter_namespace(directory, "wrong-run", timeout=5)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong run was accepted")
    assert os.readlink("/proc/self/ns/net") == origin
    assert Path("/opt/ros/noetic/setup.bash").is_file()
    report = handoff.enter_namespace(directory, "cross-distro-fixture", timeout=30)
    assert report["after"]["net"] == target["net"]
    assert report["before"]["mnt"] == report["after"]["mnt"]
    assert report["before"]["ipc"] == report["after"]["ipc"]
    assert Path("/opt/ros/noetic/setup.bash").is_file()
    payload = target["echo"].encode("ascii")
    with socket.create_connection(("127.0.0.1", target["port"]), timeout=5) as peer:
        peer.sendall(payload)
        assert receive_exact(peer, len(payload) + 3) == b"ok:" + payload
    assert source_hashes() == before
    report.update(client_distro=os.environ.get("WSL_DISTRO_NAME"), source_sha256=before,
                  loopback_echo_pass=True, noetic_filesystem_preserved=True,
                  wrong_run_rejected_before_join=True, physical_acceptance=False)
    report["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    save_result(directory, durable, "client-result.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("owner", "client"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("durable", type=Path)
    args = parser.parse_args()
    if not args.durable.is_absolute() or not args.durable.is_dir():
        raise ValueError("existing absolute durable evidence directory required")
    try:
        {"owner": owner, "client": client}[args.role](args.directory, args.durable)
    except BaseException as error:
        report = dict(status="failed", role=args.role, error=repr(error),
                      traceback=traceback.format_exc(), source_sha256=source_hashes(),
                      boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip())
        with (args.durable / (args.role + "-failure.json")).open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        raise
