"""Focused offline revalidation of the seven uncovered G1/G5 drift rows.

Evidence refresh only. Does not close G1/G5/Full. Product source is not edited.

Guards are scoped: they wrap risky imports, then restore immediately, and wrap
only the calls that need them. The suite claims zero product-surface process
or socket creation. It does not claim zero subprocess globally: the identity
test performs exactly six read-only Git metadata reads.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE_HEAD = "6eafdf9c0b734db07a9fe790c86b409d3468c10b"
EXAMPLES = REPO / "Simulator" / "wksim_runtime" / "examples"
EVIDENCE = REPO / "Simulator" / "wksim_runtime" / "independent-profile-evidence.json"
_DIALECT_ROOT = Path("/root/wksim-telemetry-dialects-20260906-3")

# Six read-only Git metadata subprocesses, all inside HeadIdentityTests:
#   1. git rev-parse HEAD
#   2. git merge-base --is-ancestor SOURCE_HEAD HEAD
#   3. git ls-tree HEAD -- <7 rows>
#   4. git diff HEAD --name-only -- <7 rows>          (staged + unstaged vs HEAD)
#   5. git diff --cached --name-only -- <7 rows>      (index vs HEAD)
#   6. git diff --name-only -- <7 rows>               (worktree vs index)
# SOURCE_HEAD is an ancestor pin: current HEAD may advance.
EXPECTED_GIT_METADATA_SUBPROCESSES = 6
_GIT_READONLY = frozenset(("rev-parse", "ls-tree", "diff", "merge-base"))

REAL_SOCKET_SOCKET = socket.socket
REAL_SUBPROCESS_RUN = subprocess.run
REAL_CTYPES_CDLL = ctypes.CDLL
REAL_OS_SYSTEM = os.system
REAL_DONT_WRITE_BYTECODE = sys.dont_write_bytecode

PINNED_ROWS = (
    (
        "Simulator/wksim_runtime/examples/arducopter-mission.json",
        "d4140c0e46f038019fd8c7de45c3ca9cd8ba612a",
        "cce5d7c77e550cb6326fbc10f83f0a657838d2c4f14ffcb730c7da56d1cbb00e",
    ),
    (
        "Simulator/wksim_runtime/examples/px4-mission.json",
        "2e7e4205c86bf15b22bd9ea748387ea3f925341b",
        "62cda2312cecd71291630b9cf64207cafbcfd0006f734ef48bb38480c0597bb6",
    ),
    (
        "Simulator/wksim_runtime/independent_profile.py",
        "9635de42839e5c535d76baa5637e270afd69dd23",
        "28816b6e330785f2d576b5fae93efc4835d2155e94e4008ca0889dfde469278c",
    ),
    (
        "Simulator/wksim_runtime/independent-profile-evidence.json",
        "33b63faa14c17488fc5468a835a8c118ffe4e13f",
        "a0f1d60b4ad5b01fb38e775f42907b2b2f1cdc3741da152b3ea81343b7015535",
    ),
    (
        "Simulator/wksim_runtime/task.py",
        "8091c15dc5ba811b4128ef715233a3fa749ef30e",
        "9791913df7ad61d229a151d4d1d0e5c2b3f32d127a7545096b43a32638f0dbbc",
    ),
    (
        "Simulator/wksim_runtime/telemetry.py",
        "33098129c6cee5d0d2b0baef9393bc7a06a35db5",
        "e62be21faeec23fd1d70932b7b25fe1d668e167af76e0b6df2624a1d42849eb0",
    ),
    (
        "Simulator/wksim_core/ap_json.py",
        "789d4a37454ceabf7702089935328696f6e28148",
        "db3498d5df50aa3ab46601a8e899c6739e613d431a7d221ac57d2a86e1846469",
    ),
)
PINNED_PATHS = tuple(path for path, _, _ in PINNED_ROWS)
EXPECTED_GIT_CALLS = (
    ("rev-parse", "HEAD"),
    ("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD"),
    ("ls-tree", "HEAD", "--") + PINNED_PATHS,
    ("diff", "HEAD", "--name-only", "--") + PINNED_PATHS,
    ("diff", "--cached", "--name-only", "--") + PINNED_PATHS,
    ("diff", "--name-only", "--") + PINNED_PATHS,
)


def _forbid(label):
    def _blocked(*args, **kwargs):
        raise AssertionError("offline slice forbids %s" % label)

    return _blocked


def _assert_stdlib_restored():
    if socket.socket is not REAL_SOCKET_SOCKET:
        raise AssertionError("socket.socket identity leaked")
    if subprocess.run is not REAL_SUBPROCESS_RUN:
        raise AssertionError("subprocess.run identity leaked")
    if ctypes.CDLL is not REAL_CTYPES_CDLL:
        raise AssertionError("ctypes.CDLL identity leaked")
    if os.system is not REAL_OS_SYSTEM:
        raise AssertionError("os.system identity leaked")
    if sys.dont_write_bytecode != REAL_DONT_WRITE_BYTECODE:
        raise AssertionError("sys.dont_write_bytecode was mutated")


def _guard_targets():
    targets = [
        ("socket.socket", _forbid("socket.socket")),
        ("socket.create_connection", _forbid("socket.create_connection")),
        ("socket.socketpair", _forbid("socket.socketpair")),
        ("subprocess.Popen", _forbid("subprocess.Popen")),
        ("subprocess.call", _forbid("subprocess.call")),
        ("subprocess.check_call", _forbid("subprocess.check_call")),
        ("subprocess.check_output", _forbid("subprocess.check_output")),
        ("subprocess.run", _forbid("subprocess.run")),
        ("os.system", _forbid("os.system")),
        ("os.popen", _forbid("os.popen")),
        ("ctypes.CDLL", _forbid("ctypes.CDLL")),
    ]
    if hasattr(socket, "create_server"):
        targets.append(("socket.create_server", _forbid("socket.create_server")))
    if hasattr(ctypes, "WinDLL"):
        targets.append(("ctypes.WinDLL", _forbid("ctypes.WinDLL")))
    if hasattr(ctypes, "PyDLL"):
        targets.append(("ctypes.PyDLL", _forbid("ctypes.PyDLL")))
    return targets


@contextmanager
def product_guards():
    """Scoped denylist. Always restores stdlib identities on exit."""
    with ExitStack() as stack:
        for name, fn in _guard_targets():
            stack.enter_context(patch(name, side_effect=fn))
        yield


def _blob_sha1(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _git_readonly(*args, allow_nonzero=False):
    if not args or args[0] not in _GIT_READONLY:
        raise RuntimeError("only read-only git metadata is allowed: %s" % (args,))
    if args[0] == "merge-base" and args != ("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD"):
        raise RuntimeError("only merge-base --is-ancestor SOURCE_HEAD HEAD is allowed: %s" % (args,))
    completed = REAL_SUBPROCESS_RUN(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True, check=False
    )
    if completed.returncode != 0 and not allow_nonzero:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), completed.stderr.strip()))
    return completed


def _read_row_identities():
    """Return HEAD/index/worktree identity for the seven rows. Exactly six git calls."""
    calls = []

    def git(*args, allow_nonzero=False):
        calls.append(args)
        return _git_readonly(*args, allow_nonzero=allow_nonzero)

    head = git("rev-parse", "HEAD").stdout.strip()
    ancestor = git("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD", allow_nonzero=True)
    if ancestor.returncode not in (0, 1):
        raise RuntimeError(
            "git merge-base --is-ancestor failed: %s" % ancestor.stderr.strip()
        )
    tree_text = git("ls-tree", "HEAD", "--", *PINNED_PATHS).stdout
    vs_head = [
        line.replace("\\", "/")
        for line in git("diff", "HEAD", "--name-only", "--", *PINNED_PATHS).stdout.splitlines()
        if line
    ]
    staged = [
        line.replace("\\", "/")
        for line in git("diff", "--cached", "--name-only", "--", *PINNED_PATHS).stdout.splitlines()
        if line
    ]
    unstaged = [
        line.replace("\\", "/")
        for line in git("diff", "--name-only", "--", *PINNED_PATHS).stdout.splitlines()
        if line
    ]
    blobs = {}
    for line in tree_text.splitlines():
        _mode, kind, blob, path = line.split(None, 3)
        if kind != "blob":
            raise RuntimeError("expected blob for %s" % path)
        blobs[path.replace("\\", "/")] = blob
    if len(calls) != EXPECTED_GIT_METADATA_SUBPROCESSES:
        raise RuntimeError("git metadata call count drifted: %s" % (calls,))
    if tuple(calls) != EXPECTED_GIT_CALLS:
        raise RuntimeError("git metadata call vector drifted: %s" % (calls,))
    return {
        "head": head,
        "ancestor_code": ancestor.returncode,
        "blobs": blobs,
        "vs_head": vs_head,
        "staged": staged,
        "unstaged": unstaged,
        "git_calls": calls,
    }


def _assert_head_and_row_identities(identities):
    """Fail closed on fork, blob drift, staged/unstaged/missing/replaced rows."""
    if identities.get("ancestor_code") != 0:
        raise AssertionError(
            "SOURCE_HEAD is not an ancestor of HEAD (merge-base --is-ancestor exit %s)"
            % identities.get("ancestor_code")
        )
    if identities.get("git_calls") != list(EXPECTED_GIT_CALLS):
        raise AssertionError("git metadata call vector drifted: %s" % (identities.get("git_calls"),))
    if len(PINNED_ROWS) != 7:
        raise AssertionError("pinned row count drifted: %s" % (len(PINNED_ROWS),))
    if identities.get("vs_head"):
        raise AssertionError("staged or unstaged drift vs HEAD: %s" % identities["vs_head"])
    if identities.get("staged"):
        raise AssertionError("staged index drift vs HEAD: %s" % identities["staged"])
    if identities.get("unstaged"):
        raise AssertionError("unstaged worktree drift vs index: %s" % identities["unstaged"])
    blobs = identities.get("blobs") or {}
    if set(blobs) != set(PINNED_PATHS):
        raise AssertionError("HEAD blob path set drifted: %s" % sorted(blobs))
    for path, blob, digest in PINNED_ROWS:
        data = (REPO / path).read_bytes()
        if blobs[path] != blob:
            raise AssertionError("HEAD blob SHA-1 drifted: %s" % path)
        if _blob_sha1(data) != blob:
            raise AssertionError("worktree blob SHA-1 drifted: %s" % path)
        if _sha256(data) != digest:
            raise AssertionError("worktree SHA-256 drifted: %s" % path)


with product_guards():
    from Simulator.wksim_core import ap_json
    from Simulator.wksim_runtime import independent_profile as profile
    from Simulator.wksim_runtime import telemetry
    from Simulator.wksim_runtime.config import ConfigError, load_config, validate_config, _unique_object
    from Simulator.wksim_runtime.mission_plan import resolve_waypoint, validate_mission
    from Simulator.wksim_runtime.task import Task, grounded, state_time, valid_state

_assert_stdlib_restored()


def _state(uav_id=1, armed=False, z=0.0, connected=True, odom_valid=True, frame="map",
           sec=10, nanosec=0, position=None, velocity=None, attitude=None):
    return NS(
        uav_id=uav_id,
        connected=connected,
        odom_valid=odom_valid,
        armed=armed,
        header=NS(frame_id=frame, stamp=NS(sec=sec, nanosec=nanosec)),
        position=list(position if position is not None else [0.0, 0.0, z]),
        velocity=list(velocity if velocity is not None else [0.0, 0.0, 0.0]),
        attitude=list(attitude if attitude is not None else [0.0, 0.0, 0.0]),
    )


class Message(NS):
    SET_PX4_MODE = 1
    ARMING = 0
    SET_CONTROL_MODE = 3
    MOVE = 4
    LAND = 3
    XYZ_VEL = 2


class VelocityFixture:
    Setup = Cmd = Message
    uav_id = 1

    def __init__(self, shared_clock, stack="px4"):
        self.flight_stack = stack
        self.use_sim_time = shared_clock
        self.boot, self.wall = 10.0, 100.0
        self.rate = 0.0
        self.yaw_checks = 0
        self.rejected = None
        self.state = _state()
        self.setup_pub = self.command_pub = NS(get_subscription_count=lambda: 1)
        self.received = {"state": self.wall}

    def fresh(self):
        return True

    def arm_ready(self, unused):
        return True

    def task_time(self):
        return self.boot if self.use_sim_time else self.wall

    def wait(self, label, predicate, timeout=20):
        self.received["state"] = self.wall + 1
        if not predicate():
            raise RuntimeError(label)

    def send(self, msg, label, timeout=10):
        if hasattr(msg, "cmd"):
            if msg.cmd == Message.ARMING:
                self.state.armed = True
            if msg.cmd == Message.SET_CONTROL_MODE:
                self.state.position[2] = 3.0
        elif msg.agent_cmd == Message.LAND:
            self.state.armed = False
            self.state.position[2] = 0.0
        else:
            self.state.velocity = list(msg.velocity_ref)
            self.rate = msg.yaw_rate_ref

    def offer_rejected(self, msg, reason, label, timeout=10):
        self.rejected = (reason, label)

    def dwell(self, label, predicate, seconds):
        for _ in range(int(seconds)):
            self.boot += 1.0
            self.wall += 1.0 / 3
            self.state.header.stamp.sec = int(self.boot)
            self.state.attitude[2] += self.rate
            if label == "yaw_rate_tracking":
                self.yaw_checks += 1
            if not predicate():
                raise RuntimeError(label + " rejected a correctly scaled native motion")


class DummySocket:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []
        self.closed = False

    def sendto(self, data, dest):
        if self.fail:
            raise OSError("receiver absent")
        self.sent.append((data, dest))
        return len(data)

    def close(self):
        self.closed = True


class FakeHeartbeat:
    def __init__(self, autopilot, msg_id=0):
        self.autopilot = autopilot
        self._msg_id = msg_id

    def get_type(self):
        return "HEARTBEAT"

    def get_msgId(self):
        return self._msg_id


class FakeModel:
    def __init__(self):
        self.calls = []

    def step(self, normalized):
        self.calls.append(list(normalized))
        state = [float(i) for i in range(90)]
        state[2] = 0.001 * len(self.calls)
        return state


class GuardScopeTests(unittest.TestCase):
    def test_stdlib_identities_restored_after_guarded_context(self):
        _assert_stdlib_restored()
        with product_guards():
            self.assertIsNot(socket.socket, REAL_SOCKET_SOCKET)
            self.assertIsNot(subprocess.run, REAL_SUBPROCESS_RUN)
            self.assertIsNot(ctypes.CDLL, REAL_CTYPES_CDLL)
            self.assertIsNot(os.system, REAL_OS_SYSTEM)
            with self.assertRaisesRegex(AssertionError, "socket.socket"):
                socket.socket()
            with self.assertRaisesRegex(AssertionError, "subprocess.run"):
                subprocess.run(["must-not-launch"])
            with self.assertRaisesRegex(AssertionError, "ctypes.CDLL"):
                ctypes.CDLL("must-not-load")
            with self.assertRaisesRegex(AssertionError, "os.system"):
                os.system("must-not-run")
        _assert_stdlib_restored()


class HeadIdentityTests(unittest.TestCase):
    def test_head_and_row_blobs_fail_closed_on_drift(self):
        identities = _read_row_identities()
        self.assertRegex(identities["head"], r"^[0-9a-f]{40}$")
        self.assertEqual(identities["ancestor_code"], 0)
        self.assertEqual(identities["git_calls"], list(EXPECTED_GIT_CALLS))
        self.assertEqual(len(identities["git_calls"]), EXPECTED_GIT_METADATA_SUBPROCESSES)
        _assert_head_and_row_identities(identities)

    def test_source_head_is_ancestor_pin_not_current_head_equality(self):
        identities = _read_row_identities()
        self.assertEqual(SOURCE_HEAD, "6eafdf9c0b734db07a9fe790c86b409d3468c10b")
        self.assertEqual(identities["ancestor_code"], 0)
        self.assertNotIn("PINNED_HEAD", globals())
        descendant = dict(identities)
        descendant["head"] = "a" * 40
        _assert_head_and_row_identities(descendant)


class HeadIdentityMutationTests(unittest.TestCase):
    def _clean_identities(self):
        identities = _read_row_identities()
        _assert_head_and_row_identities(identities)
        return identities

    def test_historical_fork_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["ancestor_code"] = 1
        with self.assertRaisesRegex(AssertionError, "not an ancestor"):
            _assert_head_and_row_identities(identities)

    def test_row_blob_sha1_drift_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["blobs"] = dict(identities["blobs"])
        path = PINNED_PATHS[0]
        identities["blobs"][path] = "0" * 40
        with self.assertRaisesRegex(AssertionError, "HEAD blob SHA-1 drifted"):
            _assert_head_and_row_identities(identities)

    def test_missing_row_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["blobs"] = dict(identities["blobs"])
        identities["blobs"].pop(PINNED_PATHS[3])
        with self.assertRaisesRegex(AssertionError, "blob path set drifted"):
            _assert_head_and_row_identities(identities)

    def test_replaced_row_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["blobs"] = dict(identities["blobs"])
        identities["blobs"][PINNED_PATHS[1]] = identities["blobs"][PINNED_PATHS[2]]
        with self.assertRaisesRegex(AssertionError, "HEAD blob SHA-1 drifted"):
            _assert_head_and_row_identities(identities)

    def test_staged_drift_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["staged"] = [PINNED_PATHS[0]]
        with self.assertRaisesRegex(AssertionError, "staged index drift"):
            _assert_head_and_row_identities(identities)

    def test_unstaged_drift_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["unstaged"] = [PINNED_PATHS[1]]
        with self.assertRaisesRegex(AssertionError, "unstaged worktree drift"):
            _assert_head_and_row_identities(identities)

    def test_vs_head_drift_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["vs_head"] = [PINNED_PATHS[2]]
        with self.assertRaisesRegex(AssertionError, "staged or unstaged drift vs HEAD"):
            _assert_head_and_row_identities(identities)

    def test_dropping_merge_base_call_fails_closed(self):
        identities = dict(self._clean_identities())
        identities["git_calls"] = [call for call in identities["git_calls"] if call[0] != "merge-base"]
        with self.assertRaisesRegex(AssertionError, "call vector drifted"):
            _assert_head_and_row_identities(identities)

    def test_write_git_verbs_are_rejected(self):
        for args in (("commit", "-m", "x"), ("reset", "--hard"), ("add", "-A"), ("clean", "-fdx")):
            with self.subTest(args=args):
                with self.assertRaisesRegex(RuntimeError, "only read-only git metadata"):
                    _git_readonly(*args)

    def test_merge_base_without_is_ancestor_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "only merge-base --is-ancestor"):
            _git_readonly("merge-base", SOURCE_HEAD, "HEAD")

    def test_reader_records_nonzero_ancestor_without_raising(self):
        tree_lines = []
        for path, blob, _digest in PINNED_ROWS:
            tree_lines.append("100644 blob %s\t%s" % (blob, path))
        responses = {
            ("rev-parse", "HEAD"): NS(returncode=0, stdout="b" * 40 + "\n", stderr=""),
            ("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD"): NS(returncode=1, stdout="", stderr=""),
            ("ls-tree", "HEAD", "--") + PINNED_PATHS: NS(returncode=0, stdout="\n".join(tree_lines) + "\n", stderr=""),
            ("diff", "HEAD", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
            ("diff", "--cached", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
            ("diff", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
        }

        def fake_run(cmd, **_kwargs):
            args = tuple(cmd[1:])
            if args not in responses:
                raise AssertionError("unexpected git argv %s" % (args,))
            return responses[args]

        with patch.object(sys.modules[__name__], "REAL_SUBPROCESS_RUN", fake_run):
            identities = _read_row_identities()
        self.assertEqual(identities["head"], "b" * 40)
        self.assertEqual(identities["ancestor_code"], 1)
        self.assertEqual(identities["git_calls"], list(EXPECTED_GIT_CALLS))
        with self.assertRaisesRegex(AssertionError, "not an ancestor"):
            _assert_head_and_row_identities(identities)

    def test_reader_accepts_descendant_head_with_frozen_blobs(self):
        tree_lines = []
        for path, blob, _digest in PINNED_ROWS:
            tree_lines.append("100644 blob %s\t%s" % (blob, path))
        descendant = "c" * 40
        responses = {
            ("rev-parse", "HEAD"): NS(returncode=0, stdout=descendant + "\n", stderr=""),
            ("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD"): NS(returncode=0, stdout="", stderr=""),
            ("ls-tree", "HEAD", "--") + PINNED_PATHS: NS(returncode=0, stdout="\n".join(tree_lines) + "\n", stderr=""),
            ("diff", "HEAD", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
            ("diff", "--cached", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
            ("diff", "--name-only", "--") + PINNED_PATHS: NS(returncode=0, stdout="", stderr=""),
        }

        def fake_run(cmd, **_kwargs):
            args = tuple(cmd[1:])
            if args not in responses:
                raise AssertionError("unexpected git argv %s" % (args,))
            return responses[args]

        with patch.object(sys.modules[__name__], "REAL_SUBPROCESS_RUN", fake_run):
            identities = _read_row_identities()
        self.assertEqual(identities["head"], descendant)
        self.assertNotEqual(identities["head"], SOURCE_HEAD)
        self.assertEqual(identities["ancestor_code"], 0)
        _assert_head_and_row_identities(identities)


class MissionFixtureTests(unittest.TestCase):
    def test_both_mission_fixtures_load_through_current_schema(self):
        expected_mission = {
            "version": 1,
            "cancel_policy": "land",
            "waypoints": [
                {"frame": "enu", "position_m": [2.0, 3.0, 3.0], "yaw_rad": 0.0, "dwell_s": 2.0},
                {"frame": "enu", "position_m": [2.0, 3.0, 3.0], "yaw_rad": math.pi / 2, "dwell_s": 2.0},
                {"frame": "body_flu", "position_m": [1.0, 0.0, 0.0], "yaw_rad": 0.0, "dwell_s": 2.0},
            ],
        }
        loaded = {}
        for stack in ("arducopter", "px4"):
            path = EXAMPLES / ("%s-mission.json" % stack)
            cfg = load_config(path)
            loaded[stack] = cfg
            self.assertEqual(cfg["stack"], stack)
            self.assertEqual(cfg["runtime_profile"], profile.PROFILE_ID)
            self.assertEqual(cfg["control_protocol"], "session_v1")
            self.assertEqual(cfg["capabilities"], ["native_position_mission"])
            self.assertEqual(cfg["mission"], expected_mission)
            self.assertEqual(validate_mission(cfg["mission"]), expected_mission)
            from Simulator.wksim_runtime import joint_profile
            independent = joint_profile.select_profile("joint_quad_dds_v1")
            mixed = joint_profile.select_profile("joint_quad_dds_mixed_pv_v1")
            self.assertEqual(cfg["model_library"], mixed["model_library"])
            self.assertNotEqual(cfg["model_library"], independent["model_library"])
            with self.assertRaisesRegex(ValueError, "model_library"):
                profile.select_config(cfg)
            resolved = resolve_waypoint(cfg["mission"]["waypoints"][2], [2.0, 3.0, 3.0], 0.0)
            self.assertEqual(resolved["position_enu_m"], [3.0, 3.0, 3.0])

        self.assertEqual(loaded["arducopter"]["ap_candidate"], "/root/wksim-ap-clock-stop-OXQqdR")
        self.assertNotIn("ap_candidate", loaded["px4"])
        self.assertEqual(loaded["px4"]["px4_root"], "/root/wksim-px4-state-ONa1Kw/src")
        self.assertNotEqual(loaded["arducopter"]["run_id"], loaded["px4"]["run_id"])

    def test_mission_schema_rejects_unknown_frame_and_cancel(self):
        base = load_config(EXAMPLES / "px4-mission.json")
        bad_mission = dict(base["mission"], cancel_policy="hold")
        with self.assertRaises(ValueError):
            validate_mission(bad_mission)
        point = dict(base["mission"]["waypoints"][0], frame="ned")
        with self.assertRaises(ValueError):
            validate_mission(dict(base["mission"], waypoints=[point]))
        with self.assertRaises(ConfigError):
            validate_config(dict(base, control_protocol="legacy_v1"))


class IndependentProfileTests(unittest.TestCase):
    def test_select_config_accepts_current_pins_and_rejects_wrong_ones(self):
        px4 = load_config(EXAMPLES / "px4-mission.json")
        del px4["model_library"]
        selected, joint = profile.select_config(px4)
        self.assertEqual(selected["runtime_profile"], profile.PROFILE_ID)
        self.assertEqual(selected["model_library"], joint["model_library"])
        self.assertEqual(joint["id"], "joint_quad_dds_v1")
        with self.assertRaisesRegex(ValueError, "Unknown independent runtime profile"):
            profile.select_config(dict(px4, runtime_profile="joint_quad_dds_v1"))
        with self.assertRaisesRegex(ValueError, "px4_root"):
            profile.select_config(dict(px4, px4_root="/root/not-the-pinned-px4/src"))
        ap = load_config(EXAMPLES / "arducopter-mission.json")
        del ap["model_library"]
        selected, _ = profile.select_config(ap)
        self.assertEqual(selected["ap_candidate"], ap["ap_candidate"])
        with self.assertRaisesRegex(ValueError, "ap_candidate"):
            profile.select_config(dict(ap, ap_candidate="/root/wrong-ap"))
        with self.assertRaisesRegex(ValueError, "mission cannot be combined"):
            profile.select_config(dict(px4, restart_control_on_ground=True))
        bare = dict(px4)
        del bare["mission"]
        with self.assertRaisesRegex(ValueError, "ground control restart"):
            profile.select_config(dict(bare, restart_control_on_ground=True))

    def test_check_profile_rejects_before_resource_inspection(self):
        px4 = load_config(EXAMPLES / "px4-mission.json")
        from Simulator.wksim_runtime import joint_profile

        with patch.object(joint_profile, "check_resources", side_effect=AssertionError("must not inspect")):
            result = profile.check_profile(dict(px4, runtime_profile="unknown"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["children_created"], 0)
        self.assertEqual(result["candidate_status"]["flown"], False)
        self.assertIn("independent_profile_rejected", [row["code"] for row in result["reasons"]])


class IndependentEvidenceTests(unittest.TestCase):
    def test_evidence_descriptor_rejects_duplicate_keys(self):
        raw = EVIDENCE.read_text(encoding="utf-8")
        self.assertIn('"schema_version": 1,', raw)
        injected = raw.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,', 1)
        with self.assertRaisesRegex(ConfigError, "Duplicate JSON key: schema_version"):
            json.loads(injected, object_pairs_hook=_unique_object)

    def test_evidence_descriptor_schema_and_local_pin_bytes(self):
        catalog = json.loads(EVIDENCE.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual(catalog["profile"], profile.PROFILE_ID)
        self.assertEqual(set(catalog["runs"]), {"px4", "arducopter"})
        for key in ("audit", "audit_source", "archive_manifest"):
            pin = catalog[key]
            self.assertEqual(set(pin), {"path", "sha256"})
            data = (REPO / pin["path"]).read_bytes()
            self.assertEqual(_sha256(data), pin["sha256"], key)
        for stack, row in catalog["runs"].items():
            self.assertRegex(row["result"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(stack, row["result"]["path"])
            self.assertGreater(len(row["files"]), 0)
        self.assertEqual(catalog["audit"]["path"],
                         "validation/promotion-flight-20260908/independent-candidate/flight-audit.json")
        self.assertIn("not complete G2/Full acceptance", profile.SCOPE)


class TaskOfflineTests(unittest.TestCase):
    def test_state_helpers_and_constructor_gates_before_ros(self):
        self.assertNotIn("rclpy", sys.modules)
        good = _state()
        self.assertEqual(state_time(good), 10.0)
        self.assertAlmostEqual(state_time(_state(sec=1, nanosec=500000000)), 1.5)
        self.assertTrue(valid_state(good))
        self.assertTrue(grounded(good))
        self.assertFalse(valid_state(None))
        self.assertFalse(valid_state(_state(connected=False)))
        self.assertFalse(valid_state(_state(odom_valid=False)))
        self.assertFalse(valid_state(_state(frame="base_link")))
        self.assertFalse(valid_state(_state(sec=0, nanosec=0)))
        self.assertFalse(valid_state(_state(velocity=[0.0, 0.0, float("nan")])))
        self.assertFalse(grounded(_state(armed=True)))
        self.assertFalse(grounded(_state(z=0.3)))
        self.assertTrue(grounded(_state(z=0.29)))
        for value in (True, "1", 1.0, None):
            with self.assertRaises(TypeError):
                valid_state(None, value)
            with self.assertRaises(TypeError):
                Task(None, None, None, "arducopter", uav_id=value)
        for value in (0, -1, 256):
            with self.assertRaises(ValueError):
                Task(None, None, None, "arducopter", uav_id=value)
        with self.assertRaises(ValueError):
            Task(None, None, None, "px4", scene_epoch=1, use_sim_time=False)
        with self.assertRaises(ValueError):
            Task(None, None, None, "px4", scene_epoch=1, use_sim_time=True, protocol="legacy_v1")
        self.assertNotIn("rclpy", sys.modules)

    def test_velocity_profile_uses_sim_or_state_motion_clock(self):
        source = (REPO / "Simulator/wksim_runtime/task.py").read_text(encoding="utf-8")
        self.assertIn(
            "motion_clock = self.task_time if self.use_sim_time else lambda: state_time(self.state)",
            source,
        )
        for shared in (False, True):
            for stack in ("px4", "arducopter"):
                with self.subTest(shared_clock=shared, stack=stack):
                    fixture = VelocityFixture(shared, stack)
                    with patch("Simulator.wksim_runtime.task.time.monotonic", side_effect=lambda: fixture.wall):
                        Task.execute_velocity_yaw(fixture)
                    self.assertEqual(fixture.yaw_checks, 4)
                    self.assertFalse(fixture.state.armed)
                    if stack == "arducopter":
                        self.assertEqual(
                            fixture.rejected,
                            ("arducopter_velocity_requires_yaw_rate_mode", "invalid_combo_rejected"),
                        )
                    else:
                        self.assertIsNone(fixture.rejected)

    def test_dwell_completes_on_state_clock_with_pump_sentinel(self):
        t = Task.__new__(Task)
        t.use_sim_time = False
        t.latest = {"state": _state(sec=10)}
        t.error = None
        phases = []
        t.phase = phases.append
        pumps = [0]
        wall = [100.0]

        def pump():
            pumps[0] += 1
            if pumps[0] > 8:
                raise AssertionError(
                    "dwell exceeded pump sentinel; state clock did not terminate the loop"
                )
            t.state.header.stamp.sec += 1

        t.pump = pump
        with patch("Simulator.wksim_runtime.task.time.monotonic", side_effect=lambda: wall[0]):
            t.dwell("boot advances without wall", lambda: True, 2)
        self.assertEqual(pumps[0], 2)
        self.assertEqual(t.state.header.stamp.sec, 12)
        self.assertEqual(phases, ["boot advances without wall"])

    def test_dwell_times_out_when_state_clock_is_frozen(self):
        t = Task.__new__(Task)
        t.use_sim_time = False
        t.latest = {"state": _state(sec=10)}
        t.error = None
        t.phase = lambda label: None
        pumps = [0]
        wall = [100.0]

        def pump():
            pumps[0] += 1
            wall[0] += 1.0
            if pumps[0] > 20:
                raise AssertionError("boot-clock deadline did not fire")

        t.pump = pump
        with patch("Simulator.wksim_runtime.task.time.monotonic", side_effect=lambda: wall[0]):
            with self.assertRaisesRegex(TimeoutError, "boot clock dwell timeout"):
                t.dwell("frozen boot", lambda: True, 2)
        self.assertEqual(pumps[0], 15)
        self.assertEqual(t.state.header.stamp.sec, 10)
        self.assertEqual(wall[0], 115.0)


class TelemetryOfflineTests(unittest.TestCase):
    def test_constructor_cannot_create_sockets_and_restores_guards(self):
        _assert_stdlib_restored()
        with product_guards():
            with patch.object(telemetry, "checked_destination", return_value="/tmp/offline/receiver.sock"), \
                    patch.object(telemetry, "load_dialect", return_value=(None, {})):
                with self.assertRaisesRegex(AssertionError, "socket.socket"):
                    telemetry.Observer(dict(
                        stack="px4",
                        telemetry_socket="/tmp/offline/receiver.sock",
                        run_id="offline-telemetry",
                        vehicle_id=1,
                    ))
        _assert_stdlib_restored()

    def test_relative_destination_is_rejected_before_socket_creation(self):
        with self.assertRaises(ValueError):
            telemetry.checked_destination("relative.sock")
        with self.assertRaises(FileNotFoundError):
            telemetry.checked_destination("/tmp/wksim-offline-missing/receiver.sock")

    @unittest.skipUnless(os.name == "posix", "Unix 0700 destination contract is not available on Windows")
    def test_posix_absent_receiver_in_owned_0700_directory(self):
        temporary = tempfile.TemporaryDirectory(prefix="wksim-g1g5-telem-")
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        os.chmod(directory, 0o700)
        if directory.stat().st_uid != os.geteuid() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
            self.skipTest("could not create an owned 0700 directory")
        absent = directory / "receiver.sock"
        self.assertEqual(telemetry.checked_destination(absent), str(absent))
        regular = directory / "not-a-socket"
        regular.write_bytes(b"x")
        os.chmod(regular, 0o600)
        with self.assertRaises(ValueError):
            telemetry.checked_destination(regular)

    def test_forward_format_and_peer_rules_without_real_sockets(self):
        destination = "/tmp/offline-g1g5/receiver.sock"
        observer = telemetry.Observer.__new__(telemetry.Observer)
        observer.config = dict(stack="px4", run_id="offline-telemetry", vehicle_id=1)
        observer.destination = destination
        observer.system_id = 22
        observer.port = 14661
        observer.peer = None
        observer.sequence = 0
        observer.counters = dict(received=0, sent=0, invalid=0, non_mavlink=0, wrong_peer=0, dropped=0)
        observer.decoder = {"source": "offline-fixture"}
        observer.gcs_target = None
        observer.gcs_forward_path = None
        observer.gcs_reverse = None
        observer.gcs_hash_log = None
        observer.gcs_packet_hashes = set()
        observer.gcs_hashes_truncated = False
        observer.output = DummySocket()
        heartbeat = [FakeHeartbeat(12)]
        packet = b"\xfd" + b"\x00" * 8
        with patch.object(telemetry, "decode_datagram", return_value=heartbeat) as decode:
            record = observer.forward(packet, ("10.0.0.1", 18591))
            self.assertIsNone(record)
            self.assertEqual(observer.counters["wrong_peer"], 1)
            self.assertIsNone(observer.forward(b"AP boot console", ("127.0.0.1", 18591)))
            self.assertEqual(observer.counters["non_mavlink"], 1)
            record = observer.forward(packet, ("127.0.0.1", 18591))
            decode.assert_called()
            self.assertEqual(observer.peer, ("127.0.0.1", 18591))
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["kind"], "native_mavlink_observation")
            self.assertEqual(record["run_id"], "offline-telemetry")
            self.assertEqual(record["vehicle_id"], 1)
            self.assertEqual(record["stack"], "px4")
            self.assertEqual(record["system_id"], 22)
            self.assertEqual(record["component_id"], 1)
            self.assertEqual(record["sequence"], 1)
            self.assertEqual(record["source"], ["127.0.0.1", 18591])
            self.assertEqual(record["message_ids"], [0])
            self.assertEqual(record["packet_base64"], base64.b64encode(packet).decode("ascii"))
            self.assertEqual(observer.counters["sent"], 1)
            self.assertEqual(observer.output.sent[0][1], destination)
            json.loads(observer.output.sent[0][0])
            observer.output = DummySocket(fail=True)
            dropped = observer.forward(packet, ("127.0.0.1", 18591))
            self.assertEqual(dropped["sequence"], 2)
            self.assertEqual(observer.counters["dropped"], 1)

    @unittest.skipUnless(
        _DIALECT_ROOT.joinpath("px4.py").is_file() and _DIALECT_ROOT.joinpath("manifest.json").is_file(),
        "pinned telemetry dialects are not present on this host; decode_datagram stays uncovered here",
    )
    def test_decode_datagram_on_available_pinned_dialect(self):
        wire = base64.b64decode(
            "/S4AADkWASIBAECtEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADQB9AH0AfQBwAEAA8eWw=="
        )
        message, = telemetry.decode_datagram(wire, 22)
        self.assertEqual(message.get_type(), "ESC_INFO")
        self.assertEqual(bytes(message.get_msgbuf()), wire)
        with self.assertRaises(ValueError):
            telemetry.decode_datagram(b"", 22)
        with self.assertRaises(ValueError):
            telemetry.decode_datagram(b"x" * (telemetry.MAX_DATAGRAM + 1), 22)


class ApJsonOfflineTests(unittest.TestCase):
    def test_sensor_fields_and_wrapper_bytes(self):
        state = list(range(90))
        fields = ap_json.sensor_fields(state)
        self.assertEqual(fields["timestamp"], 2)
        self.assertEqual(fields["imu"]["accel_body"], [61, 62, 63])
        self.assertEqual(fields["imu"]["gyro"], [64, 65, 66])
        self.assertEqual(fields["position"], [6, 7, 8])
        self.assertEqual(fields["velocity"], [3, 4, 5])
        self.assertEqual(fields["quaternion"], [12, 13, 14, 15])
        wrapped = ap_json.sensor_message(state)
        self.assertTrue(wrapped.startswith(b"\n") and wrapped.endswith(b"\n"))
        self.assertEqual(json.loads(wrapped), {
            "timestamp": 2,
            "imu": {"gyro": [64, 65, 66], "accel_body": [61, 62, 63]},
            "position": [6, 7, 8],
            "quaternion": [12, 13, 14, 15],
            "velocity": [3, 4, 5],
        })
        nan_state = list(state)
        nan_state[3] = float("nan")
        with self.assertRaises(ValueError):
            ap_json.sensor_message(nan_state)

    def test_lockstep_wrapper_uses_sensor_message_without_native_model(self):
        packet = ap_json.SERVO_PACKET.pack(18458, 1000, 0, *([1000, 1500, 2000, 0] + [1000] * 12))
        frame, rate, pwm, normalized = ap_json.decode_servos(packet)
        self.assertEqual((frame, rate), (0, 1000))
        self.assertEqual(normalized[:4], [0.0, 0.5, 1.0, 0.0])
        self.assertEqual(list(pwm[:4]), [1000, 1500, 2000, 0])
        for bad in (b"x", packet[:-1], ap_json.SERVO_PACKET.pack(18458, 0, 0, *([1000] * 16))):
            with self.assertRaises(ValueError):
                ap_json.decode_servos(bad)
        loop = ap_json.Lockstep(FakeModel())
        reply, advanced = loop.update(packet)
        self.assertTrue(advanced)
        self.assertEqual(reply, ap_json.sensor_message(loop.state))
        repeated, advanced = loop.update(packet)
        self.assertFalse(advanced)
        self.assertEqual(repeated, reply)
        self.assertEqual(loop.duplicates, 1)
        next_packet = ap_json.SERVO_PACKET.pack(18458, 1000, 1, *([1000] * 16))
        loop.update(next_packet)
        with self.assertRaises(RuntimeError):
            loop.update(ap_json.SERVO_PACKET.pack(18458, 1000, 3, *([1000] * 16)))

    def test_serve_blocked_at_native_loader_and_restores_guards(self):
        _assert_stdlib_restored()
        with product_guards():
            with self.assertRaisesRegex(AssertionError, "ctypes.CDLL|socket.socket"):
                ap_json.serve("unused-library", 19002, "unused-trace")
        _assert_stdlib_restored()


if __name__ == "__main__":
    unittest.main()
