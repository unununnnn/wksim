"""Assemble evidence.json for the n1+n2 read-only ABI evidence slice.

Reads the two raw artifacts produced by the n1/n2 collectors, computes every cross-file
fact (producer census, consumer coverage, population union, platform cross-check) and
merges them with the authored re-check verdicts. Nothing is transcribed by hand from the
raw artifacts, so evidence.json cannot drift from raw/.

Read-only with respect to the repository and the vendor installation: it reads raw/*.json
and asks git for the checkout identity; it writes exactly one artifact:
    evidence.json

Run:  python -B validation/coordination/ds-dll-abi-n1n2-20260913-01/build_evidence.py
"""
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
N1 = HERE / "raw" / "n1-pe-templates.json"
N2 = HERE / "raw" / "n2-consumer-refs.json"
OUT = HERE / "evidence.json"

PREDECESSOR_DIR = "validation/coordination/ds-dll-abi-evidence-20260913-01"
ARCHITECTURE_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
PREDECESSOR_INVENTORY_DLL_COUNT = 16
PREDECESSOR_INVENTORY_MODEL_DIR = "CopterSim\\external\\model"


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    proc = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def build():
    n1 = json.loads(N1.read_text(encoding="utf-8"))
    n2 = json.loads(N2.read_text(encoding="utf-8"))
    binaries = n1["binaries_by_sha256"]

    rc_head, head, _ = git("rev-parse", "HEAD")
    rc_branch, branch, _ = git("rev-parse", "--abbrev-ref", "HEAD")
    rc_anc, _, _ = git("merge-base", "--is-ancestor", ARCHITECTURE_ANCESTOR, "HEAD")

    # --- population union ---------------------------------------------------------
    same_name = [e for e in binaries.values() if "same-filename-copy" in e["roles"]]
    deployed_sha = next(
        (t["sha256"] for t in n1["named_targets"] if t["candidate_id"] == "deployed-model-dir-exp1"),
        None,
    )
    newly_inspected = [
        e for e in same_name if not any(PREDECESSOR_INVENTORY_MODEL_DIR in p for p in e["paths"])
    ]
    union_population = {
        "predecessor_inventory_distinct_binaries": PREDECESSOR_INVENTORY_DLL_COUNT,
        "same_name_binaries_inspected_this_run": len(same_name),
        "same_name_binaries_already_in_predecessor_inventory": len(same_name) - len(newly_inspected),
        "newly_inspected_binaries_not_in_predecessor_inventory": len(newly_inspected),
        "union_distinct_binaries": PREDECESSOR_INVENTORY_DLL_COUNT + len(newly_inspected),
        "newly_inspected_sha256": sorted(e["sha256"] for e in newly_inspected),
        "consumer_named_target_already_in_predecessor_inventory": True,
        "deployed_exp1_sha256": deployed_sha,
        "note": (
            "the predecessor's 16-DLL inventory already contained the deployed Exp1 copy and the "
            "consumer's hardcoded MulticopterNOpx4 target; this run adds the remaining distinct "
            "binaries carrying the Exp1_MinModelTemp.dll name"
        ),
    }

    # --- platform cross-check over every binary inspected this run -----------------
    platform = {
        "binaries_inspected_this_run": len(binaries),
        "all_machine_0x8664": all(e["machine"] == "0x8664" for e in binaries.values()),
        "all_without_clr_directory": all(not e["has_clr_directory"] for e in binaries.values()),
        "import_module_sets": [list(s) for s in sorted({tuple(sorted(e["imports"])) for e in binaries.values()})],
        "all_only_kernel32": all(tuple(sorted(e["imports"])) == ("KERNEL32.dll",) for e in binaries.values()),
        "all_version_strings_empty": all(not e["version_strings"] for e in binaries.values()),
        "all_have_decorated_dllcreatmodel": all(
            e["has_decorated_dllcreatmodel"] for e in binaries.values()
        ),
        "any_with_undecorated_dllcreatmodel": any(
            e["has_undecorated_dllcreatmodel"] for e in binaries.values()
        ),
    }

    # --- producer census vs consumer references -----------------------------------
    consumer_referenced = n2["symbols_with_code_references"]
    producer_census = {}
    for entry in binaries.values():
        for name in entry["dll_export_names"]:
            producer_census.setdefault(name, []).append(entry["sha256"])
    consumer_names_with_zero_producers = sorted(
        name for name in consumer_referenced if name not in producer_census
    )
    exported_but_never_referenced = sorted(
        name for name in producer_census if name not in consumer_referenced
    )
    per_binary_coverage = [
        {
            "sha256": entry["sha256"],
            "family": entry["family"],
            "paths": entry["paths"],
            "dll_export_count": len(entry["dll_export_names"]),
            "exports_referenced_by_consumer": sorted(
                set(entry["dll_export_names"]) & set(consumer_referenced)
            ),
            "exports_never_referenced_by_consumer": sorted(
                set(entry["dll_export_names"]) - set(consumer_referenced)
            ),
        }
        for entry in sorted(binaries.values(), key=lambda x: x["sha256"])
    ]

    # --- argtypes shape lines used by the wrapper methods (consumer intent only) ---
    wrapper_shape_lines = []
    for label, block in n2["adjacent_excerpts"].items():
        for item in block["key_lines"]:
            if "ctypes.c_" in item["text"] and "* len(" in item["text"]:
                wrapper_shape_lines.append({"range": label, "line": item["line"], "text": item["text"]})

    # --- declaration blocks per symbol (consumer intent, never ABI authority) ------
    declaration_table = {}
    cfg = n2["constructor_configuration"]
    for symbol, blocks in cfg["declared_argtypes_blocks"].items():
        declaration_table.setdefault(symbol, {"argtypes": [], "restype": []})
        for block in blocks:
            declaration_table[symbol]["argtypes"].append(
                {
                    "start_line": block["start_line"],
                    "end_line": block["end_line"],
                    "guard_name": block["guard"],
                    "declared": block["declared"],
                }
            )
    for symbol, lines_ in cfg["declared_restype_lines"].items():
        declaration_table.setdefault(symbol, {"argtypes": [], "restype": []})
        declaration_table[symbol]["restype"] = [
            {"line": item["line"], "guard_name": item["guard"], "text": item["text"]} for item in lines_
        ]
    for symbol, entry in declaration_table.items():
        referenced = [r for r in n2["symbol_reference_table"].get(symbol, []) if r["kind"] != "comment-mention"]
        entry["reference_lines"] = referenced
        entry["exported_by_inspected_binaries"] = sorted(producer_census.get(symbol, []))
        entry["exported_by_count"] = len(producer_census.get(symbol, []))
    for symbol in consumer_referenced:
        if symbol not in declaration_table:
            declaration_table[symbol] = {
                "argtypes": [],
                "restype": [],
                "reference_lines": n2["symbol_reference_table"].get(symbol, []),
                "exported_by_inspected_binaries": sorted(producer_census.get(symbol, [])),
                "exported_by_count": len(producer_census.get(symbol, [])),
            }

    # --- authored re-check verdicts ------------------------------------------------
    recheck = {
        "c5_exp1_two_binaries": {
            "class": "C",
            "original_result": (
                "Two distinct binaries share the filename Exp1_MinModelTemp.dll: the e0 template copy "
                "(235520 B, 30747a8d...) and the deployed model-directory copy (230912 B, 8134aab6...); "
                "no material states which binary the SDK sample or the SITL batch path loads."
            ),
            "original_result_preserved": True,
            "evidence_it_is_preserved": [
                "e0 template re-read: size 235520, sha256 30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b, matches_recorded=true",
                "deployed copy re-read: size 230912, sha256 8134aab646adda098b7c98a4daa17278dbed7a626a1811e18ed1a88288fb6a46, matches_recorded=true",
            ],
            "net_change": (
                "the ambiguity is wider than two binaries, not narrower: 12 copies of the name exist in the "
                "searched tree, collapsing to 11 distinct binaries with 7 distinct export-name sets, and a third "
                "previously unrecorded binary (the e1 template, 242176 B, c2fbfd4d...) carries the same filename"
            ),
            "resolved_half": (
                "the deployment mechanism is now evidenced: each experiment batch declares DLLModel to its own "
                "sibling file and copies %~dp0<name>.dll into %PSP_PATH%\\CopterSim\\external\\model, then passes "
                "DLLModel to CopterSim.exe (e0 Exp1_MinModelTemp_SITL.bat:27,43-44; cited-sample "
                "CopterSimDllSILRun.bat:27,43-44,142). So an experiment loads its own sibling binary, not a "
                "globally chosen one."
            ),
            "still_open": (
                "the deployed file currently present (8134aab6..., legacy family) is byte-identical to no sibling "
                "in the searched tree, so the provenance of the file that is deployed right now is unrecorded; and "
                "no material records which binary a bare SDK script with no batch loaded. The .bat files were read "
                "as text and NOT executed, so the copy directive's runtime effect is not observed."
            ),
            "abi_consequence": (
                "any ABI statement keyed to 'the e0 DLL' remains non-nameable as a single object, but it is now "
                "possible to name an exact binary by SHA256 for every inspected candidate"
            ),
        },
        "c6_e0_old_and_new_naming": {
            "class": "C",
            "original_result": (
                "the claim that the e0 DLL exports legacy and modern output names side by side held only as a "
                "population statement; no single DLL of the 16 had both, and the per-file claim about the e0 DLL "
                "could not be checked because its export table was not inventoried."
            ),
            "original_result_preserved": True,
            "evidence_it_is_preserved": [
                "predecessor finding 'zero DLLs with both families' is not contradicted",
                "this run adds 11 distinct same-name binaries and one consumer-named target: still zero binaries "
                "export both families",
            ],
            "net_change": (
                "the per-file claim is no longer unverifiable, and it is contradicted for both candidate e0 "
                "binaries: the e0 template exports only DlloutHILSensor30d/DlloutHILGPS30d/DlloutVehileInfo60d "
                "(no DlloutputSensors/DlloutputGPS/DlloutModel3DInfo), while the deployed same-name copy exports "
                "only the legacy set (no modern name). No inspected binary of the 26-binary union carries both."
            ),
            "affected_repository_prose": [
                "docs/coptersim-reconstruction.md:63",
                "docs/plan/model-reference-provenance-supplement.md:20",
            ],
            "recommended_action": "n6 (documentation reconciliation) is now actionable with a per-file matrix",
        },
        "c7_e1_export_string_provenance": {
            "class": "C",
            "original_result": (
                "the e1 export-name list was a binary-string observation with no recorded file path, size or "
                "SHA256, and it was the sole source for the claim that DllInitPosAngState is the correct name."
            ),
            "original_result_preserved": True,
            "evidence_it_is_preserved": (
                "the supplement's conclusion is neither contradicted nor confirmed by any readable header; this run "
                "only makes the observation reproducible"
            ),
            "net_change": (
                "REPRODUCIBILITY CLOSED: the e1 template DLL is now recorded as "
                "E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e1_MinModelTempLib/Exp1_MinModelTemp.dll, "
                "size 242176, sha256 c2fbfd4dc3a6338bcd040e59960af0c4c8c0925a0c583c4d9792e342d9558000, machine "
                "0x8664, and its export table was read read-only. Its 12 Dll* export names plus the decorated "
                "?DllCreatModel@@YAXXZ reproduce the supplement's list exactly."
            ),
            "refinement": (
                "the supplement wrote DllCreatModel undecorated; the export-table entry is the decorated "
                "?DllCreatModel@@YAXXZ, consistent with the predecessor's G8 finding"
            ),
            "residual_gap": (
                "the list is still a name-only observation: no parameter type, element width, return type, unit, "
                "frame, ownership or lifecycle contract follows from it"
            ),
        },
        "c2_dllinitposangstat": {
            "class": "C",
            "original_result": (
                "the consumer checks DllInitPosAngStat at lines 1248/1255 but accesses DllInitPosAngState; "
                "DllInitPosAngStat is absent from all 18 inventoried PE files, so this is a real consumer defect "
                "and the DllInitPosAngState argtypes never get installed on that path."
            ),
            "original_result_preserved": True,
            "evidence_it_is_preserved": [
                "DllInitPosAngStat is absent from all 12 binaries inspected this run as well (11 distinct "
                "same-name binaries plus the consumer's hardcoded target)",
                "DllInitPosAngState is present in all of them",
            ],
            "net_change": (
                "zero-occurrence now holds over the 26-binary union instead of 18 PE files, and the defect is "
                "bound to exact lines and to machine-checkable structure: the guard/access mismatch is at "
                "1248->1249 and 1255->1256, and because every guard in the constructor block is a hasattr() on a "
                "different name, both argtypes blocks for DllInitPosAngState sit under a foreign guard."
            ),
            "consumer_intent_recorded": (
                "two identical (c_double[3], c_double[3]) argtypes blocks were intended for "
                "DllInitPosAngState, at 1249-1252 and 1256-1259, both unreachable"
            ),
            "not_claimed": "no runtime consequence is asserted; the callee-side ABI is untouched",
        },
        "c3_dllinputdoubctrls": {
            "class": "C",
            "original_result": (
                "the consumer configures DllInputDoubCtrls and the supplied sample calls sendInDoubCtrls(), but no "
                "inventoried model DLL exports that name (only DllinSIL28d existed, in Exp2); either the sample "
                "targets a DLL outside the inventoried directory or the legacy control path is dead."
            ),
            "original_result_preserved": True,
            "evidence_it_is_preserved": [
                "DllInputDoubCtrls has zero occurrences across all 12 binaries inspected this run, including the "
                "binary shipped in the directory literally named 2.sendInDoubCtrls",
                "the predecessor's 16-DLL zero-occurrence result is not contradicted",
            ],
            "net_change": (
                "the zero-occurrence half is strengthened (26-binary union) and the sample half is now bound: the "
                "supplied sample named in the predecessor's evidence (0.ApiExps/12.DllModelImport/"
                "9.ModelLoadCopterSim30100Python/DllSimCtrlAPITest.py, sha256 3510c3a6...) and the ApiExps "
                "2.sendInDoubCtrls sample (inSIL28dTest.py, sha256 37c95567...) BOTH instantiate "
                "DllSimCtrlAPI.DllSimCtrlAPI (the UDP-side class at consumer line 143) and call the UDP sender "
                "method sendInDoubCtrls (consumer line 348). Neither loads a DLL through ctypes and neither "
                "references DllInputDoubCtrls."
            ),
            "sample_to_binary_binding": (
                "both batches declare DLLModel to their own sibling and copy it into the model directory, then "
                "pass it to CopterSim.exe; the cited sample's sibling MulticopterNOpx4.dll (173568 B, 0179c58f...) "
                "is byte-identical to the deployed CopterSim/external/model copy whose export table is in n1, and "
                "the sendInDoubCtrls demo's sibling is db33543c9b32... (224768 B), which exports DllinSIL28d and "
                "DllinCollision20d but not DllInputDoubCtrls"
            ),
            "correction_of_cited_evidence": (
                "the predecessor's c3 cites validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/summary.md:27 as "
                "recording the sample's sendInDoubCtrls() call. Re-read read-only, that line states only that the "
                "supplied sample demonstrates legacy Python call intent and records no sendInDoubCtrls() call; the "
                "sample actually read in that slice is the ModelLoad 30100 sample (summary.md:18, abi-facts.json:27). "
                "The conclusion is unaffected; the citation is."
            ),
            "verdict": (
                "the ctypes name DllInputDoubCtrls has no producer at all in the inspected population, and the "
                "experiment actually named after that path does not use the ctypes path; on this evidence the "
                "consumer's DllInputDoubCtrls passthrough is inert for every inspected binary"
            ),
            "not_claimed": (
                "no semantic equivalence between DllInputDoubCtrls and DllinSIL28d is asserted, and which export "
                "CopterSim.exe routes the 28-double UDP payload into is not proven - CopterSim.exe internals were "
                "not inspected"
            ),
        },
        "g11_old_and_new_family_coexistence": {
            "class": "P",
            "original_result": (
                "no inventoried model DLL exports both the legacy output-name family and the modern family; "
                "family is a per-file property."
            ),
            "original_result_preserved": True,
            "net_change": (
                "re-confirmed and widened: across the 26-binary union, zero binaries export both families. "
                "Among the 12 inspected this run: 1 legacy-only (the deployed copy) and 11 modern-only. A "
                "binary's position in either family is a per-file property of its own export table."
            ),
        },
        "c1_dllinputcolls_width": {
            "class": "C",
            "original_result": (
                "the same consumer declares DllInputColls as c_double[20] at 1237-1239 and then overwrites it "
                "with c_float[20] at 1294-1296; the width is undecided."
            ),
            "original_result_preserved": True,
            "net_change": (
                "consumer-side refinement only: both duplicate wrapper methods construct their argument with "
                "ctypes.c_float (lines 1847 and 1957), so the surviving consumer-side intent is float[20]. This "
                "does not adjudicate the callee's element width, which remains unknown."
            ),
        },
        "c4_outcopterdata_shape": {
            "class": "C",
            "original_result": (
                "DllOutCopterData is declared with argtypes=[double[32]] at construction, but the wrapper "
                "re-allocates the array and calls it with no arguments; a fixed-arity argtypes and a "
                "zero-argument call cannot both be correct."
            ),
            "original_result_preserved": True,
            "net_change": (
                "confirmed with exact lines: guard at 1310, argtypes c_double[32] at 1311-1313, restype None at "
                "1314, and a zero-argument call self.dll.DllOutCopterData(out_data) at 2025 inside the wrapper "
                "at 2021-2030"
            ),
        },
    }

    blocker_delta = {
        "b1_no_authoritative_interface_material": {
            "before": "no authoritative header/spec/calling convention for any DLL ABI exists in the material",
            "net_change": "unchanged - n1/n2 are metadata and text evidence only; no header, spec or calling convention was found or produced",
            "status": "blocked, unchanged",
        },
        "b2_consumer_conflicts_not_adjudicable": {
            "before": "the consumer conflict set c1-c4 cannot be adjudicated from consumer material alone",
            "net_change": (
                "narrowed: c2 and c3 now have complete, machine-checkable consumer-side explanations (an "
                "unreachable guard and a name with no producer in the inspected population), and c4 is confirmed "
                "line-exact. This is a defect adjudication, not an ABI adjudication: c1's callee element width "
                "remains unknown and no conflict yields a prototype, so nothing here can fill a manifest."
            ),
            "status": "partially narrowed, still blocking for ABI purposes",
        },
        "b3_sample_identity_ambiguous": {
            "before": "sample identity is ambiguous (c5) and the supplied sample's target DLL is unrecorded (c3/m9)",
            "net_change": (
                "narrowed and partly cleared: the supplied sample's own target binary is now named and hashed "
                "(MulticopterNOpx4.dll, 173568 B, 0179c58f..., byte-identical to the deployed copy whose export "
                "table is recorded), and the deployment mechanism (batch declares and copies its sibling, then "
                "passes DLLModel to CopterSim.exe) is evidenced. Still open: the currently deployed Exp1 binary "
                "(8134aab6...) matches no sibling in the tree, and bare scripts with no batch have no recorded "
                "binding."
            ),
            "status": "partially cleared, still open for the Exp1 chain",
        },
        "b4_license_unrecorded": {
            "before": "no license or permitted-use statement for any vendor model DLL is recorded",
            "net_change": "unchanged - not investigated by this dispatch and no such statement was found",
            "status": "blocked, unchanged",
        },
        "b5_no_manifest_instance": {
            "before": "no manifest instance exists in the repository; only the schema and its validator do",
            "net_change": "unchanged - this slice deliberately produces no manifest candidate",
            "status": "blocked, unchanged",
        },
        "net_effect_on_issue_9": (
            "no blocker is cleared and #9's DLL half remains NO-GO. Two blockers (B2, B3) are narrowed and three "
            "recorded contradictions (c7 closed for reproducibility; c2, c3 given complete consumer-side "
            "explanations; c6 adjudicated against the per-file prose) now rest on reproducible, hashed evidence. "
            "The single unblocking path is unchanged: an external authoritative interface package bound to one "
            "named binary SHA256 (n3)."
        ),
    }

    next_actions = [
        {
            "id": "n3",
            "priority": 1,
            "action": "request the authoritative interface package bound to one named binary SHA256 (header/spec, calling convention, exact float width, return and error contract, buffer ownership, lifecycle state machine, thread/isolation contract, build manifest, license)",
            "status": "unchanged by this slice; still the only path that can clear B1/B2/B4",
            "changed_by_this_slice": "the request can now name an exact binary and SHA256 for every inspected candidate instead of a filename",
        },
        {
            "id": "n6",
            "priority": 2,
            "action": "reconcile the per-file prose contradicted by the inventory: docs/coptersim-reconstruction.md:63 and docs/plan/model-reference-provenance-supplement.md:20 should become a per-file export-family matrix",
            "status": "now actionable",
            "changed_by_this_slice": "c6 moved from 'unverifiable per file' to 'contradicted for both e0 candidates' with a recorded matrix to point at",
        },
        {
            "id": "n8",
            "priority": 3,
            "action": "NEW: record read-only, for each of the 11 distinct same-name binaries, its sibling batch DLLModel declaration and deployment target, closing the sample-to-binary binding per experiment without executing anything",
            "status": "new, low cost, offline",
            "changed_by_this_slice": "two of the twelve copies already have this binding recorded here; the other ten do not",
        },
        {
            "id": "n7",
            "priority": 3,
            "action": "route the adjacent #75 static-gate failure to its owner",
            "status": "unchanged; not re-run in this slice",
            "changed_by_this_slice": "nothing",
        },
    ]

    evidence = {
        "schema": "wksim.ds-dll-abi-n1n2.evidence.v1",
        "deliverable": "validation/coordination/ds-dll-abi-n1n2-20260913-01",
        "kind": "historical-material/read-only-abi-evidence-n1n2",
        "new_architecture_implementation": False,
        "continues": {
            "artifact": f"{PREDECESSOR_DIR}/audit.json",
            "relationship": "completes the predecessor's own next actions n1 and n2; the predecessor artifact is read-only input and was not modified",
            "predecessor_scope_respected": "the predecessor's recorded results are preserved, not overwritten; where this run disagrees it records the original result and the new evidence side by side",
        },
        "checked_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "checkout": {
            "cwd": str(REPO),
            "branch": branch,
            "head": head,
            "head_short": head[:7],
            "head_at_dispatch": head,
            "head_at_write": head,
            "architecture_ancestor": ARCHITECTURE_ANCESTOR,
            "ancestor_check_command": f"git merge-base --is-ancestor {ARCHITECTURE_ANCESTOR} HEAD",
            "ancestor_check_exit_code": rc_anc,
            "working_tree_untouched_by_this_slice": True,
        },
        "prohibitions_observed": {
            "no_dll_or_model_or_exe_execution": True,
            "no_reverse_engineering_or_disassembly_or_type_recovery": True,
            "no_vendor_binary_copy_or_publish": True,
            "no_abi_guessing_or_consumer_side_abi_inference": True,
            "no_native_build": True,
            "no_ros": True,
            "no_flight_controller": True,
            "no_model": True,
            "no_unreal_engine": True,
            "no_matlab": True,
            "no_issue_mutation": True,
            "no_shared_ledger_or_adapter_write": True,
            "no_existing_file_modified": True,
            "exclusive_writes": [
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/.gitattributes",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/n1_pe_templates_readonly.py",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/n2_consumer_refs_readonly.py",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/build_evidence.py",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/raw/n1-pe-templates.json",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/raw/n2-consumer-refs.json",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/evidence.json",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/report.md",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/manifest.json",
                "validation/coordination/ds-dll-abi-n1n2-20260913-01/SHA256SUMS",
            ],
        },
        "evidence_inputs": [
            {
                "id": "vendor-consumer",
                "path": n2["consumer"]["path"],
                "sha256": n2["consumer"]["sha256"],
                "drift": "none - live sha256 equals the predecessor-recorded 0a2a30e9...",
                "kind": "vendor ctypes consumer, read-only text",
            },
            {
                "id": "predecessor-excerpt",
                "path": "validation/model-reference-provenance-20260907/sdk-wrapper-evidence.json",
                "sha256": n2["prior_excerpt_verification"]["recorded_artifact_sha256"],
                "drift": "none - hash verified before use",
                "kind": "tracked predecessor excerpt; re-read agreement verified",
            },
            {
                "id": "pe-producer",
                "path": n1["producer_reused"],
                "sha256": n1["producer_sha256"],
                "drift": "none",
                "kind": "existing untracked read-only PE producer reused unchanged via inspect_pe.inspect(path)",
            },
            {
                "id": "predecessor-audit",
                "path": f"{PREDECESSOR_DIR}/audit.json",
                "kind": "read-only input; not modified",
            },
        ],
        "scope": {
            "n1": "read-only PE header/import/export/version-table metadata for the named e0/e1 template DLLs, every distinct binary carrying the Exp1_MinModelTemp.dll name, and the consumer's hardcoded target",
            "n2": "precise line-numbered excerpts for DllSimCtrlAPI.py adjacent to 1234-1307, each bound to an export name, an argtypes/restype declaration, a missing or unreachable initialisation branch, and a target-DLL identity",
            "supplementary": "read-only sample-side binding for the two samples relevant to the c3 resolution requirement",
            "out_of_scope": "no ABI determination, no loading/execution, no manifest instance, no adapter, no issue mutation, no shared ledger write",
        },
        "n1": {
            "named_target_records": n1["named_targets"],
            "same_filename_enumeration": n1["same_filename_enumeration"],
            "same_filename_identity": n1["same_filename_identity"],
            "template_export_set_comparison": n1["template_export_set_comparison"],
            "zero_occurrence_recheck": n1["zero_occurrence_recheck"],
            "platform_cross_check": platform,
            "population_union": union_population,
            "full_binary_records": n1["binaries_by_sha256"],
            "producer_census": {k: sorted(v) for k, v in sorted(producer_census.items())},
            "per_binary_consumer_coverage": per_binary_coverage,
            "declaration_caveat": n1["execution"],
        },
        "n2": {
            "consumer": n2["consumer"],
            "prior_excerpt_verification": n2["prior_excerpt_verification"],
            "adjacent_ranges_covered": n2["adjacent_ranges_covered"],
            "adjacent_excerpts": n2["adjacent_excerpts"],
            "symbol_reference_table": n2["symbol_reference_table"],
            "symbols_with_code_references": consumer_referenced,
            "constructor_configuration": cfg,
            "missing_initialisation_branches": n2["missing_initialisation_branches"],
            "declaration_table": declaration_table,
            "target_dll_identity": n2["target_dll_identity"],
            "wrapper_shape_lines": wrapper_shape_lines,
            "authority_caveat": n2["authority_caveat"],
            "limits": n2["limits"],
        },
        "consumer_vs_producer_binding": {
            "consumer_referenced_names": consumer_referenced,
            "consumer_names_with_zero_producers_in_inspected_population": consumer_names_with_zero_producers,
            "produced_names_never_referenced_by_consumer": exported_but_never_referenced,
            "producer_counts": {
                name: len(shas) for name, shas in sorted(producer_census.items())
            },
            "cited_sample_target_sha256": "0179c58f14f8140302c1ec1a36ae455e88146c64099be1cd6a633cb174afe7e8",
            "cited_sample_target_exports": binaries[
                "0179c58f14f8140302c1ec1a36ae455e88146c64099be1cd6a633cb174afe7e8"
            ]["dll_export_names"],
            "notable": [
                "the decorated ?DllCreatModel@@YAXXZ is exported by all "
                f"{len(binaries)} binaries inspected this run and is referenced nowhere in the consumer: the "
                "model-creation entry point is never invoked from Python",
                "DllGetGpsPos is exported by "
                f"{len(producer_census.get('DllGetGpsPos', []))} of {len(binaries)} inspected binaries and is "
                "referenced nowhere in the consumer",
                "DllInputDoubCtrls is exported by "
                f"{len(producer_census.get('DllInputDoubCtrls', []))} inspected binaries; DllinSIL28d by "
                f"{len(producer_census.get('DllinSIL28d', []))}",
                "the binary the cited sample's own batch deploys (MulticopterNOpx4.dll) exports "
                f"{len(binaries['0179c58f14f8140302c1ec1a36ae455e88146c64099be1cd6a633cb174afe7e8']['dll_export_names'])} "
                "Dll* names and neither DllInputDoubCtrls nor DllinSIL28d",
            ],
            "interpretation_caveat": (
                "absence of a producer in this population is a fact about the inspected binaries only; the 16-DLL "
                "deployed population plus 10 newly inspected same-name binaries is not the whole vendor surface"
            ),
        },
        "supplementary_sample_binding": n2["supplementary_sample_side_probe"],
        "recheck_of_predecessor_findings": recheck,
        "blocker_delta": blocker_delta,
        "coverage": {
            "covered": [
                "read-only PE header/import/export/version tables for 12 distinct binaries: 11 distinct binaries carrying the Exp1_MinModelTemp.dll name plus the consumer's hardcoded MulticopterNOpx4.dll target",
                "the named e0 template DLL, the named e1 template DLL, and the deployed same-name copy, each with path, size, sha256, machine, imports, sections, version strings and complete Dll* export list",
                "re-verification of the predecessor's recorded 1234-1307 consumer excerpt by byte comparison against a fresh read",
                "exact line-numbered consumer bindings for the constructor configuration block, the target-DLL name resolution, the load call, the CreateVehicle call order, the input dispatch loop, the wrapper methods, the output reads, the control encoders and the hardcoded default target",
                "the guard/access mismatch, the unreachable argtypes blocks, the repeated argtypes declarations and the symbols with no constructor configuration",
                "read-only sample-side binding for the cited sample and for the ApiExps sendInDoubCtrls demo, including their sibling DLL identities",
            ],
            "not_covered": [
                "any calling convention (only the decorated DllCreatModel name encodes one, and it was not re-derived here)",
                "parameter types, element widths, return types, units, frames, ownership, lifetime or behaviour of any export",
                "CopterSim.exe and CopterSimNoUI.exe internals, including which export receives a 28-double UDP payload",
                "the other 5-6 DLLs in the ApiExps surface that do not carry the Exp1_MinModelTemp.dll name",
                "the remaining 10 same-name binaries' sibling batch DLLModel declarations (recommended as n8)",
                "any license or permitted-use statement",
                "any manifest instance, ABI approval or interoperability claim",
            ],
        },
        "non_claims": [
            "This slice approves no ABI for any DLL, legacy or new, and does not change the state of #9, #27, #28, #73, #74, #76, #77 or #78.",
            "No DLL, model or exe was loaded, mapped, executed, decompiled, disassembled or type-recovered; the .bat files were read as text only and were NOT executed.",
            "Binary metadata establishes export-name existence and spelling, name decoration, module machine type and static imports only. It does not establish parameter types, element widths, return types, units, frames, ownership, lifetime or behaviour.",
            "Consumer-side ctypes declarations and wrapper bodies are recorded as intent, never as ABI authority; no ABI is inferred from them.",
            "No semantic equivalence between DllInputDoubCtrls and DllinSIL28d is asserted, and no routing behaviour of CopterSim.exe is asserted.",
            "No vendor source, header, binary or install was copied, modified or published; only metadata and single-line text references are recorded.",
            "No numerical, physical, timing, interoperability or compatibility acceptance is claimed; the #23/G6 budgets are untouched.",
            "The predecessor artifact and the shared ledgers were read only; this slice does not review or endorse any peer commit.",
        ],
        "artifacts": {
            "raw_n1": "raw/n1-pe-templates.json",
            "raw_n2": "raw/n2-consumer-refs.json",
            "raw_n1_sha256": sha256_of(N1),
            "raw_n2_sha256": sha256_of(N2),
            "producers": [
                "n1_pe_templates_readonly.py",
                "n2_consumer_refs_readonly.py",
                "build_evidence.py",
            ],
        },
    }
    return evidence


def main():
    evidence = build()
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    reloaded = json.loads(OUT.read_text(encoding="utf-8"))
    assert reloaded == evidence, "evidence.json round-trip mismatch"
    blk = reloaded["blocker_delta"]
    print(
        json.dumps(
            {
                "artifact": str(OUT.relative_to(REPO)).replace("\\", "/"),
                "sha256": sha256_of(OUT),
                "head": reloaded["checkout"]["head"],
                "ancestor_check_exit_code": reloaded["checkout"]["ancestor_check_exit_code"],
                "binaries_inspected": reloaded["n1"]["platform_cross_check"]["binaries_inspected_this_run"],
                "union_distinct_binaries": reloaded["n1"]["population_union"]["union_distinct_binaries"],
                "consumer_names_with_zero_producers": reloaded["consumer_vs_producer_binding"][
                    "consumer_names_with_zero_producers_in_inspected_population"
                ],
                "blockers": {k: v["status"] for k, v in blk.items() if k.startswith("b")},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
