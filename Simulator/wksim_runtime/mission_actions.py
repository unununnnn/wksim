"""Local per-offer pause/resume submission; publication is NOT completion.

One runtime-owned mailbox remembers consumed tokens for its lifetime. Runtime
must issue fresh tokens and process/epoch identities and check current offers.
Status has no freshness heartbeat: no cross-process monotonic-clock inference
is made here. Status can change after the final check and before publication;
only runtime feedback confirms an action. Trusted local directories and the
shared filesystem checks are not a hostile administrator security boundary.
"""

import json
import os
import re
import tempfile
import threading
import uuid

from .mission_cancel import _directory, _read, MAX_REQUEST_BYTES


_FIELDS = {"version", "run_id", "mission_id", "control_epoch",
           "native_generation", "action_token", "request_id", "action"}
_ACTIONS = ("pause", "resume")


def _hex(value, name):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError(name + " must be 32 lowercase hex characters")


def _identity(run_id, mission_id):
    if any(not isinstance(v, str) or not v for v in (run_id, mission_id)):
        raise ValueError("explicit nonempty run_id and mission_id are required")


def _offer(token, epoch, generation, actions):
    _hex(token, "action_token")
    _hex(epoch, "control_epoch")
    if type(generation) is not int or generation < 0:
        raise ValueError("native_generation must be a nonnegative integer")
    if not isinstance(actions, list) or any(a not in _ACTIONS for a in actions):
        raise ValueError("allowed_actions must be a list of pause/resume actions")


def _request(value, run_id, mission_id, token, epoch, generation, actions):
    if set(value) != _FIELDS:
        raise ValueError("request fields must exactly match the schema")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("unsupported request version")
    if value["run_id"] != run_id or value["mission_id"] != mission_id:
        raise ValueError("request identity mismatch")
    _hex(value["action_token"], "action_token")
    _hex(value["control_epoch"], "control_epoch")
    _hex(value["request_id"], "request_id")
    if (type(value["native_generation"]) is not int or
            value["native_generation"] < 0):
        raise ValueError("invalid request native_generation")
    if (value["action_token"] != token or value["control_epoch"] != epoch or
            value["native_generation"] != generation):
        raise ValueError("request offer mismatch")
    if value["action"] not in _ACTIONS or value["action"] not in actions:
        raise ValueError("action is not allowed for this offer")
    return value


def _status(directory, run_id, mission_id, token, action):
    value = _read(directory / "mission-status.json", 1024 * 1024)
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("unsupported status version")
    if value.get("run_id") != run_id or value.get("mission_id") != mission_id:
        raise ValueError("status identity mismatch")
    epoch, generation = value.get("control_epoch"), value.get("native_generation")
    actions = value.get("allowed_actions")
    _offer(value.get("action_token"), epoch, generation, actions)
    if value["action_token"] != token or action not in actions:
        raise ValueError("status does not allow the requested offer/action")
    return epoch, generation, actions


class ActionMailbox:
    """Return each valid token once per instance; retain all request files.

    Invalid requests append distinct reasons to rejections without consuming
    the opportunity. Runtime must keep this instance for the mission lifetime.
    """

    def __init__(self, directory, run_id, mission_id):
        _identity(run_id, mission_id)
        self.directory = directory
        self.run_id, self.mission_id = run_id, mission_id
        self.rejections = []
        self._consumed = set()
        self._lock = threading.Lock()

    def poll(self, token, control_epoch, native_generation, allowed_actions) -> dict | None:
        with self._lock:
            try:
                _offer(token, control_epoch, native_generation, allowed_actions)
                if token in self._consumed:
                    return None
                directory = _directory(self.directory)
                try:
                    value = _read(directory / ("mission-action-" + token + ".json"),
                                  MAX_REQUEST_BYTES)
                except FileNotFoundError:
                    return None
                value = _request(value, self.run_id, self.mission_id, token,
                                 control_epoch, native_generation, allowed_actions)
            except (OSError, ValueError, RecursionError) as exc:
                reason = str(exc)
                if reason not in self.rejections:
                    self.rejections.append(reason)
                return None
            self._consumed.add(token)
            return value


def request_action(directory, run_id, mission_id, action_token, action, *, expected_offer=None) -> dict:
    """Atomically submit or return the identical existing action request.

    Submission is NOT action completion. Raises ValueError/OSError on invalid
    status, conflicts or unsafe files. Requires same-directory hard links;
    never overwrites a request and provides no command transport or fallback.
    Optional expected_offer pins the epoch/generation that a caller confirmed;
    a newer status can never silently upgrade that confirmed identity.
    """
    _identity(run_id, mission_id)
    _hex(action_token, "action_token")  # Validate before constructing any path.
    if action not in _ACTIONS:
        raise ValueError("action must be pause or resume")
    directory = _directory(directory)
    offer = _status(directory, run_id, mission_id, action_token, action)
    epoch, generation, _ = offer
    if expected_offer is not None:
        if (not isinstance(expected_offer, dict) or set(expected_offer) != {'control_epoch', 'native_generation'}
                or type(expected_offer['native_generation']) is not int
                or expected_offer != dict(control_epoch=epoch, native_generation=generation)):
            raise ValueError('confirmed offer identity changed before publication')
    target = directory / ("mission-action-" + action_token + ".json")

    def existing():
        return _request(_read(target, MAX_REQUEST_BYTES), run_id, mission_id,
                        action_token, epoch, generation, [action])

    try:
        return existing()
    except FileNotFoundError:
        pass
    value = dict(version=1, run_id=run_id, mission_id=mission_id,
                 control_epoch=epoch, native_generation=generation,
                 action_token=action_token, request_id=uuid.uuid4().hex, action=action)
    payload = (json.dumps(value, ensure_ascii=True) + "\n").encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds byte limit")
    fd, temporary = tempfile.mkstemp(prefix=".mission-action-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _directory(directory)
        if _status(directory, run_id, mission_id, action_token, action) != offer:
            raise ValueError("status offer changed before publication")
        try:
            os.link(temporary, target)
        except FileExistsError:
            return existing()
        return value
    finally:
        os.unlink(temporary)
