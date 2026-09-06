"""Local cancellation submission only; no DDS or flight-control operations.

The runtime must create a fresh uuid4().hex mission_id for each mission/run,
independently of control_epoch, and own one CancelMailbox for that mission.
Requests remain on disk for auditing/idempotence; consumption is in memory.
Directories are trusted local collaboration space, not an administrator-proof
security boundary. Concurrent status transitions can race submission: only the
runtime's subsequent status records confirm cancellation.
"""

import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import uuid


REQUEST_FILE = "mission-cancel.json"
STATUS_FILE = "mission-status.json"
MAX_REQUEST_BYTES = 4096
_FIELDS = {"version", "run_id", "mission_id", "request_id", "action"}
_ACTIVE = {"accepted", "takeover", "running", "pausing", "paused", "resuming", "cancelling", "landing"}
_TERMINAL = {"completed", "failed", "cancelled"}


class CancelRequestError(ValueError):
    """A request or local mailbox does not meet the cancellation contract."""


def _not_link(info):
    # Windows junctions and other reparse points must not redirect the mailbox.
    return not (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(directory):
    path = Path(os.path.abspath(os.fspath(directory)))
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if not _not_link(info) or not stat.S_ISDIR(info.st_mode):
            raise CancelRequestError("directory must not follow symlinks/reparse points")
    return path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CancelRequestError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise CancelRequestError("invalid JSON constant: " + value)


def _read(path, limit):
    before = path.lstat()
    if not _not_link(before) or not stat.S_ISREG(before.st_mode):
        raise CancelRequestError("file must be regular and not a symlink/reparse point")
    if before.st_size > limit:
        raise CancelRequestError("file exceeds byte limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or
                not os.path.samestat(before, opened)):
            raise CancelRequestError("file changed while opening")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise CancelRequestError("file exceeds byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CancelRequestError("invalid JSON: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise CancelRequestError("JSON must be an object")
    return value


def _identity(run_id, mission_id):
    if any(not isinstance(item, str) or not item for item in (run_id, mission_id)):
        raise CancelRequestError("explicit nonempty run_id and mission_id are required")


def _request(value, run_id, mission_id):
    if set(value) != _FIELDS:
        raise CancelRequestError("request fields must exactly match the schema")
    if type(value["version"]) is not int or value["version"] != 1:
        raise CancelRequestError("unsupported request version")
    if value["run_id"] != run_id or value["mission_id"] != mission_id:
        raise CancelRequestError("request identity mismatch")
    if value["action"] != "cancel":
        raise CancelRequestError("invalid action")
    if not isinstance(value["request_id"], str) or not re.fullmatch(
            r"[0-9a-fA-F]{32}", value["request_id"]):
        raise CancelRequestError("request_id must be a 32-hex UUID")
    return value


def _status(directory, run_id, mission_id):
    value = _read(directory / STATUS_FILE, 1024 * 1024)
    if type(value.get("version")) is not int or value["version"] != 1:
        raise CancelRequestError("unsupported status version")
    if value.get("run_id") != run_id or value.get("mission_id") != mission_id:
        raise CancelRequestError("status identity mismatch")
    sequence = value.get("update_sequence")
    if type(sequence) is not int or sequence < 0:
        raise CancelRequestError("invalid status update_sequence")
    state = value.get("state")
    if not isinstance(state, str):
        raise CancelRequestError("invalid status state")
    if state in _TERMINAL:
        raise CancelRequestError("mission is terminal: " + state)
    if state not in _ACTIVE:
        raise CancelRequestError("unknown status state")


class CancelMailbox:
    """Poll one explicit identity; invalid files never interrupt the mission.

    rejections contains distinct human-readable reasons. Invalid requests are
    retained, and can be corrected by the directory owner. A valid request is
    returned at most once over this object's lifetime, even if the file changes.
    """

    def __init__(self, directory, run_id, mission_id):
        _identity(run_id, mission_id)
        self.directory = directory
        self.run_id = run_id
        self.mission_id = mission_id
        self.rejections = []
        self._consumed = False
        self._lock = threading.Lock()

    def poll(self) -> dict | None:
        with self._lock:
            if self._consumed:
                return None
            try:
                directory = _directory(self.directory)
                try:
                    value = _read(directory / REQUEST_FILE, MAX_REQUEST_BYTES)
                except FileNotFoundError:
                    return None
                value = _request(value, self.run_id, self.mission_id)
            except (OSError, ValueError, RecursionError) as exc:
                reason = str(exc)
                if reason not in self.rejections:
                    self.rejections.append(reason)
                return None
            self._consumed = True
            return value


def request_cancel(directory, run_id, mission_id) -> dict:
    """Publish or return an existing valid request; never overwrite a file.

    Raises CancelRequestError/OSError on rejection. Requires a filesystem with
    same-directory hard links (e.g. NTFS/ext4); no partial-write fallback.
    """
    _identity(run_id, mission_id)
    directory = _directory(directory)
    _status(directory, run_id, mission_id)
    target = directory / REQUEST_FILE
    try:
        return _request(_read(target, MAX_REQUEST_BYTES), run_id, mission_id)
    except FileNotFoundError:
        pass
    value = dict(version=1, run_id=run_id, mission_id=mission_id,
                 request_id=uuid.uuid4().hex, action="cancel")
    payload = (json.dumps(value, ensure_ascii=True) + "\n").encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise CancelRequestError("request exceeds byte limit")
    fd, temporary = tempfile.mkstemp(prefix=".mission-cancel-", suffix=".tmp",
                                     dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _directory(directory)
        _status(directory, run_id, mission_id)
        try:
            os.link(temporary, target)
        except FileExistsError:
            return _request(_read(target, MAX_REQUEST_BYTES), run_id, mission_id)
        return value
    finally:
        os.unlink(temporary)
