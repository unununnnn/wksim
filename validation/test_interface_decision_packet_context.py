"""Offline admission contract for the historical #9/#29 decision packet.

The packet is context, not decision authority.  These tests bind its bytes to
the two existing JSON observations, record the later display-manifest reader,
and keep the unrelated #83 diagnostic evidence outside this packet's scope.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKET_REL = "docs/coordination/ds-interface-decision-packet-20260912.md"
NOTE_REL = "docs/coordination/interface-decision-packet-ingest-note-20260914.md"
DEFER_REL = "docs/plan/9-vendor-abi-defer-boundary.json"
AUDIT_REL = "validation/coordination/ds-dll-abi-evidence-20260913-01/audit.json"
DISPLAY_REL = "Simulator/wksim_runtime/display_scene_binding.py"
PACKET_SHA256 = "a7cfe224f2528a5651c6037eae7cf1547ae57e1dfe210c7792308ad247d5e382"
NOTE_SHA256 = "e1e8171fc6ab46dba28b94ac550eca1893e9d844ddf22b46252f382742302632"
DIAGNOSTIC_COMMIT = "e8defc1d8317892e022ee24de086b026c1317e5a"


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def strict_loads(text: str):
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=lambda value: _finite_float(value),
    )


def _finite_float(value: str) -> float:
    number = float(value)
    if number == float("inf") or number == float("-inf"):
        raise ValueError(f"non-finite JSON number: {value}")
    return number


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _matching_path_records(value, target: str):
    matches = []
    if isinstance(value, dict):
        if value.get("path") == target:
            matches.append(value)
        for child in value.values():
            matches.extend(_matching_path_records(child, target))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_matching_path_records(child, target))
    return matches


def _display_entrypoints(source: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "DisplaySceneBinding":
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def _validate_context(packet: bytes, note: str, defer, audit, display_source: str):
    if _sha256(packet) != PACKET_SHA256:
        raise ValueError("decision packet SHA-256 drift")

    defer_matches = _matching_path_records(defer, PACKET_REL)
    audit_matches = _matching_path_records(audit, PACKET_REL)
    if len(defer_matches) != 1 or len(audit_matches) != 1:
        raise ValueError("decision packet must occur exactly once in each JSON pin")
    for record in defer_matches + audit_matches:
        if record.get("sha256") != PACKET_SHA256:
            raise ValueError("decision packet JSON SHA-256 drift")
    if defer_matches[0].get("tracked") is not False:
        raise ValueError("defer record must preserve the historical untracked observation")
    if audit_matches[0].get("tracked") is not True:
        raise ValueError("audit record must preserve its expected tracked observation")

    required_note_text = (
        "只把它接入为历史上下文和证据来源，不把它提升为决策依据",
        "不授予 #9、#26、#29、#33、#84、Full、G6 或 Goal 的验收与关闭资格",
        "差异仅在跟踪状态的观测时点与语义，不能用来推导新的接口决定",
        "“唯一读取方”陈述过期",
        "两组证据主题、schema 和验收作用均不同，不能互相替代",
        DIAGNOSTIC_COMMIT,
    )
    for text in required_note_text:
        if text not in note:
            raise ValueError(f"ingest note lost required boundary: {text}")

    packet_text = packet.decode("utf-8")
    stale_claim = (
        "`wksim.display-manifest.v1` 目前唯一的读取方是离线审计器 "
        "`tools/audit_29_terrain_evidence.py`"
    )
    if stale_claim not in packet_text:
        raise ValueError("historical unique-reader claim is missing")
    if DISPLAY_REL not in note or "已被后续已跟踪实现" not in note:
        raise ValueError("ingest note does not supersede the unique-reader claim")
    if not {"load_manifest", "validate_manifest"}.issubset(
        _display_entrypoints(display_source)
    ):
        raise ValueError("tracked display binding lost manifest entrypoints")


class InterfaceDecisionPacketContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = (ROOT / PACKET_REL).read_bytes()
        cls.note_bytes = (ROOT / NOTE_REL).read_bytes()
        cls.note = cls.note_bytes.decode("utf-8")
        cls.defer_text = (ROOT / DEFER_REL).read_text(encoding="utf-8")
        cls.audit_text = (ROOT / AUDIT_REL).read_text(encoding="utf-8")
        cls.defer = strict_loads(cls.defer_text)
        cls.audit = strict_loads(cls.audit_text)
        cls.display_source = (ROOT / DISPLAY_REL).read_text(encoding="utf-8")

    def validate(self, **changes):
        values = {
            "packet": self.packet,
            "note": self.note,
            "defer": copy.deepcopy(self.defer),
            "audit": copy.deepcopy(self.audit),
            "display_source": self.display_source,
        }
        values.update(changes)
        _validate_context(**values)

    def test_original_hashes_and_context_contract(self):
        self.assertEqual(_sha256(self.note_bytes), NOTE_SHA256)
        self.validate()

    def test_display_binding_is_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", DISPLAY_REL],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), DISPLAY_REL)

    def test_json_pins_reject_duplicate_keys(self):
        for text in (self.defer_text, self.audit_text):
            with self.subTest():
                with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                    strict_loads('{"schema":"first",' + text.lstrip()[1:])

    def test_json_pins_reject_non_finite_numbers(self):
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(ValueError, "non-finite"):
                    strict_loads('{"value":' + literal + "}")

    def test_path_hash_and_tracking_drift_fail_closed(self):
        defer = copy.deepcopy(self.defer)
        record = _matching_path_records(defer, PACKET_REL)[0]
        record["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 drift"):
            self.validate(defer=defer)

        audit = copy.deepcopy(self.audit)
        record = _matching_path_records(audit, PACKET_REL)[0]
        record["tracked"] = False
        with self.assertRaisesRegex(ValueError, "expected tracked observation"):
            self.validate(audit=audit)

    def test_duplicate_packet_record_fails_closed(self):
        audit = copy.deepcopy(self.audit)
        audit["duplicate_decision_packet"] = copy.deepcopy(
            _matching_path_records(audit, PACKET_REL)[0]
        )
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.validate(audit=audit)

    def test_authority_or_acceptance_promotion_fails_closed(self):
        promoted = self.note.replace("不把它提升为决策依据", "把它提升为决策依据")
        with self.assertRaisesRegex(ValueError, "lost required boundary"):
            self.validate(note=promoted)
        accepted = self.note.replace("不授予 #9", "授予 #9")
        with self.assertRaisesRegex(ValueError, "lost required boundary"):
            self.validate(note=accepted)

    def test_supersession_and_diagnostic_boundaries_fail_closed(self):
        stale = self.note.replace("“唯一读取方”陈述过期", "“唯一读取方”陈述仍有效")
        with self.assertRaisesRegex(ValueError, "lost required boundary"):
            self.validate(note=stale)
        conflated = self.note.replace("不能互相替代", "可以互相替代")
        with self.assertRaisesRegex(ValueError, "lost required boundary"):
            self.validate(note=conflated)

    def test_missing_display_entrypoint_fails_closed(self):
        source = self.display_source.replace("def load_manifest(", "def load_manifest_removed(")
        with self.assertRaisesRegex(ValueError, "lost manifest entrypoints"):
            self.validate(display_source=source)


if __name__ == "__main__":
    unittest.main()
