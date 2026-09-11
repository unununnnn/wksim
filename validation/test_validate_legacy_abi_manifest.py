"""Pure offline tests for the legacy ABI manifest proposal gate (#27/#73).

The only valid fixture is a structurally complete BLOCKED proposal; no test
may construct an accepted manifest, because this gate cannot grant acceptance.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import validate_legacy_abi_manifest as gate

SCHEMA = ROOT / "docs/plan/27-legacy-abi-manifest.schema.json"
SDK_SHA = gate.SDK_WRAPPER_SHA256


def valid_proposal():
    """A structurally complete proposal; still blocked and unapproved."""
    return {
        "schema_version": 1,
        "kind": "legacy_abi_manifest_proposal",
        "status": "blocked_unapproved",
        "acceptance": False,
        "sample": {
            "file_sha256": "30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b",
            "source": "vendor SDK sample directory, local read-only",
            "license": "vendor license text on file; redistribution rights unverified",
            "permitted_local_use": "local validation only, no redistribution",
            "readable_header_or_wrapper": "RflySimSDK/ctrl/DllSimCtrlAPI.py",
        },
        "exports": [
            {
                "name": "DllInitPosAngState",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok", "nonzero=fault"]},
                "parameters": [
                    {"name": "pos_ang", "order": 0, "type": "pointer",
                     "direction": "in",
                     "array_layout": {"is_array": True, "element_type": "double", "length": 12}},
                ],
                "ownership": "caller",
                "units": "pos [m], ang [rad]; unresolved mapping to root state",
                "sample_phase": "init",
                "step_semantics": "not_step_bound",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1248-1255"},
            },
            {
                "name": "DllInputColls",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok"]},
                "parameters": [
                    {"name": "values", "order": 0, "type": "pointer",
                     "direction": "in",
                     "array_layout": {"is_array": True, "element_type": "double",
                                      "length": 20}},
                ],
                "ownership": "caller",
                "units": "mixed; per-element units unresolved pending conflict adjudication",
                "sample_phase": "pre_step",
                "step_semantics": "input_committed_before_step",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1235-1239,1292-1296"},
            },
            {
                "name": "Dllstep",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok", "nonzero=step fault"]},
                "parameters": [
                    {"name": "model", "order": 0, "type": "pointer",
                     "direction": "inout",
                     "array_layout": {"is_array": False, "element_type": "none",
                                      "length": 0}},
                ],
                "ownership": "caller",
                "units": "dimensionless step counter; model time in seconds",
                "sample_phase": "pre_step",
                "step_semantics": "input_committed_before_step",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1242-1244"},
            },
            {
                "name": "DlloutVehileInfo60d",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok"]},
                "parameters": [
                    {"name": "info", "order": 0, "type": "pointer",
                     "direction": "out",
                     "array_layout": {"is_array": True, "element_type": "double",
                                      "length": 60}},
                ],
                "ownership": "caller",
                "units": "60d vehicle state; unresolved per-element unit breakdown",
                "sample_phase": "post_step",
                "step_semantics": "output_sampled_after_step",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1270-1275"},
            },
            {
                "name": "DllReInitModel",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok", "nonzero=reset fault"]},
                "parameters": [],
                "ownership": "none",
                "units": "dimensionless control call; resets internal model state",
                "sample_phase": "reset",
                "step_semantics": "not_step_bound",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1245-1247"},
            },
            {
                "name": "DllDestroyModel",
                "calling_convention": "cdecl",
                "return": {"type": "int32", "error_codes": ["0=ok"]},
                "parameters": [],
                "ownership": "none",
                "units": "dimensionless teardown call",
                "sample_phase": "terminate",
                "step_semantics": "not_step_bound",
                "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py", "sha256": SDK_SHA,
                             "lines": "1240-1241"},
            },
        ],
        "lifecycle": {
            "states": ["unloaded", "loaded", "initialized", "stepping",
                       "resetting", "terminated"],
            "transitions": ["unloaded->loaded", "loaded->initialized",
                            "initialized->stepping", "stepping->resetting",
                            "resetting->initialized", "stepping->terminated"],
            "reset_restores_random_state": "evidence_required",
        },
        "isolation": {
            "dll_crash": "host subprocess exit marks optional run failed only",
            "step_error": "nonzero return freezes the optional run; no retry",
            "short_output": "short read is a hard error; never zero-filled",
            "repeated_reset": "second reset without terminate is rejected",
            "thread_udp_residue": "process group teardown verified empty",
        },
        "unresolved_conflicts": [
            {"id": "dllinputcolls-width",
             "description": "DllInputColls declared double[20] then overwritten as float[20] in the SDK consumer",
             "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py",
                          "sha256": SDK_SHA, "lines": "1235-1239,1292-1296"},
             "adjudication": "unresolved"},
            {"id": "dllinitposang-name",
             "description": "consumer checks DllInitPosAngStat but accesses DllInitPosAngState",
             "evidence": {"path": "RflySimSDK/ctrl/DllSimCtrlAPI.py",
                          "sha256": SDK_SHA, "lines": "1248-1255"},
             "adjudication": "unresolved"},
        ],
    }


class ManifestGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "manifest.json"

    def write(self, manifest):
        self.path.write_text(json.dumps(manifest), encoding="utf-8")
        return self.path

    def write_raw(self, raw_text):
        self.path.write_text(raw_text, encoding="utf-8")
        return self.path

    def test_valid_blocked_proposal_passes_still_unapproved(self):
        report = gate.validate(self.write(valid_proposal()))
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["gate"], "proposal_structure_only")
        self.assertEqual(report["status"], "blocked_unapproved")
        self.assertIs(report["acceptance"], False)

    def test_report_bytes_are_deterministic(self):
        path = self.write(valid_proposal())
        self.assertEqual(gate.serialize(gate.validate(path)),
                         gate.serialize(gate.validate(path)))

    def test_schema_self_check(self):
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(
            json.loads(SCHEMA.read_text(encoding="utf-8")))

    def test_self_declared_acceptance_rejected(self):
        manifest = valid_proposal()
        manifest["status"] = "accepted"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("schema" in v for v in report["violations"]))
        manifest = valid_proposal()
        manifest["acceptance"] = True
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("schema" in v for v in report["violations"]))

    def test_missing_known_conflict_rejected(self):
        manifest = valid_proposal()
        manifest["unresolved_conflicts"] = manifest["unresolved_conflicts"][:1]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("unresolved_conflicts must exactly match" in v or "schema" in v
                            for v in report["violations"]))

    def test_adjudicated_conflict_rejected(self):
        manifest = valid_proposal()
        manifest["unresolved_conflicts"][0]["adjudication"] = "resolved: float"
        report = gate.validate(self.write(manifest))
        self.assertTrue(report["violations"])

    def test_conflict_without_pinned_evidence_rejected(self):
        manifest = valid_proposal()
        manifest["unresolved_conflicts"][0]["evidence"]["sha256"] = "0" * 64
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("pinned SDK consumer" in v for v in report["violations"]))

    def test_duplicate_conflict_ids_rejected(self):
        manifest = valid_proposal()
        manifest["unresolved_conflicts"].append(dict(manifest["unresolved_conflicts"][0]))
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("duplicate conflict ids" in v or "schema" in v
                            for v in report["violations"]))

    def test_sample_chain_placeholders_rejected(self):
        for key in ("license", "permitted_local_use", "readable_header_or_wrapper"):
            manifest = valid_proposal()
            manifest["sample"][key] = "unknown"
            report = gate.validate(self.write(manifest))
            self.assertTrue(any(f"sample.{key}" in v for v in report["violations"]),
                            key)

        # Ordinary printable Unicode is allowed in descriptive fields, while
        # required strings reject blank values.
        manifest = valid_proposal()
        manifest["sample"]["source"] = "供应商 SDK 样例"
        self.assertEqual(gate.validate(self.write(manifest))["violations"], [])
        manifest["sample"]["source"] = " \t "
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("blank or whitespace-only" in v for v in report["violations"]))

    def test_isolation_placeholders_rejected(self):
        for key in ("dll_crash", "step_error", "short_output", "repeated_reset",
                    "thread_udp_residue"):
            for placeholder in ("unknown", " TODO ", "N/A"):
                manifest = valid_proposal()
                manifest["isolation"][key] = placeholder
                report = gate.validate(self.write(manifest))
                self.assertTrue(any(f"isolation.{key}" in v for v in report["violations"]),
                                (key, placeholder))

        manifest = valid_proposal()
        manifest["isolation"]["dll_crash"] = "host\u200bprocess exit"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("forbidden Unicode categories" in v for v in report["violations"]))

        # Placeholder checks compare NFKC + casefold forms without rewriting.
        manifest = valid_proposal()
        manifest["isolation"]["dll_crash"] = "ｕｎｋｎｏｗｎ"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("isolation.dll_crash" in v for v in report["violations"]))

    def test_placeholders_are_rejected_in_all_nested_required_strings(self):
        cases = (
            ("exports[0].return.type", lambda m: m["exports"][0]["return"].update(type="unknown")),
            ("exports[0].return.error_codes", lambda m: m["exports"][0]["return"].update(error_codes=[" N/A "])),
            ("exports[0].parameters[0].name", lambda m: m["exports"][0]["parameters"][0].update(name="ＴＯＤＯ")),
            ("exports[0].evidence.path", lambda m: m["exports"][0]["evidence"].update(path="N/A")),
        )
        for where, mutate in cases:
            with self.subTest(where=where):
                manifest = valid_proposal()
                mutate(manifest)
                report = gate.validate(self.write(manifest))
                self.assertTrue(any(where in violation for violation in report["violations"]),
                                (where, report["violations"]))

    def test_placeholder_near_words_and_unicode_descriptions_are_allowed(self):
        manifest = valid_proposal()
        manifest["exports"][0]["return"]["type"] = "unknown_state"
        manifest["exports"][0]["return"]["error_codes"] = ["N/A_ERROR"]
        manifest["exports"][0]["parameters"][0]["name"] = "todo_count"
        manifest["exports"][0]["evidence"]["path"] = "vendor/todo.txt"
        manifest["isolation"]["dll_crash"] = "TODO items remain documented; N/A is not a value here"
        manifest["sample"]["source"] = "供应商 SDK 样例"
        report = gate.validate(self.write(manifest))
        self.assertEqual(report["violations"], [])

    def test_export_semantic_gates(self):
        # Empty error_codes rejected
        manifest = valid_proposal()
        manifest["exports"][0]["return"]["error_codes"] = []
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("error_codes" in v for v in report["violations"]))

        # Array parameter without positive length rejected
        manifest = valid_proposal()
        manifest["exports"][1]["parameters"][0]["array_layout"]["length"] = 0
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("positive length" in v for v in report["violations"]))

        # Array parameter with non-pointer type rejected
        manifest = valid_proposal()
        manifest["exports"][1]["parameters"][0]["type"] = "float"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("pointer" in v for v in report["violations"]))

        # Out-of-order parameters rejected
        manifest = valid_proposal()
        manifest["exports"][0]["parameters"][0]["order"] = 1
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("order" in v for v in report["violations"]))

        # Duplicate parameter names rejected
        manifest = valid_proposal()
        p0 = dict(manifest["exports"][0]["parameters"][0])
        p1 = dict(p0, order=1)
        manifest["exports"][0]["parameters"] = [p0, p1]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("duplicate parameter names" in v for v in report["violations"]))

        # Bad ownership rejected
        manifest = valid_proposal()
        manifest["exports"][0]["ownership"] = "nobody-knows"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("schema" in v for v in report["violations"]))

        # Bad step_semantics rejected
        manifest = valid_proposal()
        manifest["exports"][0]["step_semantics"] = "whenever"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("schema" in v for v in report["violations"]))

        # Empty units rejected
        manifest = valid_proposal()
        manifest["exports"][0]["units"] = ""
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("units" in v for v in report["violations"]))

    def test_duplicate_exports_rejected(self):
        manifest = valid_proposal()
        manifest["exports"].append(dict(manifest["exports"][0]))
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("duplicate export" in v or "schema" in v
                            for v in report["violations"]))

    def test_missing_lifecycle_export_phase_rejected(self):
        # Missing terminate export
        manifest = valid_proposal()
        manifest["exports"] = [e for e in manifest["exports"] if e["name"] != "DllDestroyModel"]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("terminate" in v for v in report["violations"]))

        # Missing init export
        manifest = valid_proposal()
        manifest["exports"] = [e for e in manifest["exports"] if e["name"] != "DllInitPosAngState"]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("init" in v for v in report["violations"]))

    def test_lifecycle_transitions_graph_validation(self):
        # Malformed transition syntax
        manifest = valid_proposal()
        manifest["lifecycle"]["transitions"][0] = "bad_transition_syntax"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("transition" in v for v in report["violations"]))

        # Transition with unknown state
        manifest = valid_proposal()
        manifest["lifecycle"]["transitions"][0] = "unloaded->unknown_state"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("declared states" in v or "schema" in v for v in report["violations"]))

        # Every declared state must be reachable from unloaded, not merely
        # mentioned as a transition endpoint somewhere in the graph.
        manifest = valid_proposal()
        manifest["lifecycle"]["transitions"] = [
            "unloaded->loaded", "loaded->initialized", "initialized->stepping",
            "stepping->terminated", "resetting->initialized",
        ]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("not reachable from 'unloaded'" in v for v in report["violations"]))

        # The schema and semantic gate both require all six lifecycle states.
        manifest = valid_proposal()
        manifest["lifecycle"]["states"] = manifest["lifecycle"]["states"][:-1]
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("six required states" in v or "schema" in v
                            for v in report["violations"]))

    def test_clean_relative_path_enforcement(self):
        # Absolute path rejected
        manifest = valid_proposal()
        manifest["sample"]["readable_header_or_wrapper"] = "/usr/include/wrapper.h"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("relative" in v or "schema" in v for v in report["violations"]))

        # Windows drive root rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["path"] = "C:/wrapper.h"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("relative" in v or "schema" in v for v in report["violations"]))

        # Backslashes rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["path"] = "vendor\\wrapper.h"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("backslash" in v or "schema" in v for v in report["violations"]))

        # Traversal .. rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["path"] = "vendor/../secret.h"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("traversal" in v or "schema" in v for v in report["violations"]))

        # NUL byte rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["path"] = "vendor/wrapper.h\0.exe"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("NUL" in v or "schema" in v for v in report["violations"]))

        # Raw path spelling is strict: dot segments, empty segments, and
        # whitespace are rejected before Path normalization can hide them.
        for bad_path in ("./vendor/wrapper.h", "vendor/./wrapper.h",
                         "vendor//wrapper.h", "vendor/wrapper.h/", "vendor/ wrapper.h",
                         "vendor/wrapper\u200b.h", "ｖendor/wrapper.h"):
            manifest = valid_proposal()
            manifest["exports"][0]["evidence"]["path"] = bad_path
            report = gate.validate(self.write(manifest))
            self.assertTrue(report["violations"], bad_path)

    def test_evidence_lines_ascending_check(self):
        # Inverted line range rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["lines"] = "100-50"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("ascending" in v for v in report["violations"]))

        # Evidence line numbers are one-based.
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["lines"] = "0-10"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("schema" in v or ">= 1" in v for v in report["violations"]))

    def test_known_conflict_description_and_path_are_pinned(self):
        for field, value in (("description", "changed description"),
                             ("path", "other/sdk.py")):
            manifest = valid_proposal()
            if field == "description":
                manifest["unresolved_conflicts"][0][field] = value
            else:
                manifest["unresolved_conflicts"][0]["evidence"][field] = value
            report = gate.validate(self.write(manifest))
            self.assertTrue(any("pinned SDK-consumer" in v or "evidence path" in v or "schema" in v
                                for v in report["violations"]), field)

        # Descending segments rejected
        manifest = valid_proposal()
        manifest["exports"][0]["evidence"]["lines"] = "200-210,150-160"
        report = gate.validate(self.write(manifest))
        self.assertTrue(any("ascending" in v for v in report["violations"]))

    def test_lexical_duplicate_json_keys_rejected(self):
        raw = json.dumps(valid_proposal()).replace(
            '"calling_convention": "cdecl"',
            '"calling_convention": "stdcall", "calling_convention": "cdecl"'
        )
        report = gate.validate(self.write_raw(raw))
        self.assertTrue(any("duplicate JSON key" in v for v in report["violations"]))

        top_dup = json.dumps(valid_proposal()).replace(
            '"schema_version": 1',
            '"schema_version": 999, "schema_version": 1'
        )
        report = gate.validate(self.write_raw(top_dup))
        self.assertTrue(any("duplicate JSON key" in v for v in report["violations"]))

    def test_lexical_nan_and_infinity_rejected(self):
        for bad_const in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(bad=bad_const):
                raw = json.dumps(valid_proposal()).replace('"length": 20', f'"length": {bad_const}')
                report = gate.validate(self.write_raw(raw))
                self.assertTrue(any("disallowed JSON constant" in v or "readable JSON" in v for v in report["violations"]))

    def test_missing_file_and_symlink_rejected(self):
        report = gate.validate(self.path)
        self.assertTrue(report["violations"])
        target = self.write(valid_proposal())
        link = Path(self.dir.name) / "link.json"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        self.assertTrue(gate.validate(link)["violations"])

    def test_cli_exit_codes(self):
        path = self.write(valid_proposal())
        ok = subprocess.run([sys.executable, "-B",
                             str(ROOT / "tools/validate_legacy_abi_manifest.py"),
                             str(path)], capture_output=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stderr.decode())
        report = json.loads(ok.stdout.decode())
        self.assertEqual(report["gate"], "proposal_structure_only")
        self.assertEqual(report["status"], "blocked_unapproved")
        self.assertIs(report["acceptance"], False)

        bad = valid_proposal()
        bad["unresolved_conflicts"] = []
        bad_path = self.write(bad)
        failed = subprocess.run([sys.executable, "-B",
                                 str(ROOT / "tools/validate_legacy_abi_manifest.py"),
                                 str(bad_path)], capture_output=True, timeout=60)
        self.assertEqual(failed.returncode, 2)
        self.assertIn("unresolved_conflicts", failed.stdout.decode())


if __name__ == "__main__":
    unittest.main()
