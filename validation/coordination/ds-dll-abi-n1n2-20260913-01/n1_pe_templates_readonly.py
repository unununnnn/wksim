"""n1: read-only PE header/import/export/version-table inventory for the named e0/e1
template DLLs, the deployed same-name copy, and every distinct binary that carries the
file name Exp1_MinModelTemp.dll in the searched vendor tree.

Why the enumeration: the predecessor audit (ds-dll-abi-evidence-20260913-01) recorded an
identity ambiguity (c5) between two binaries sharing the name Exp1_MinModelTemp.dll and
recorded that DllInitPosAngStat / DllInputDoubCtrls have zero occurrences in a 16-DLL
population (c2/c3). The vendor tree turns out to contain many more copies of that exact
name, including directories named after the very APIs in question
(.../11.inSILAPI/3.inSIL28d/2.sendInDoubCtrls/). Bounding those two zero-occurrence
claims honestly requires reading the export tables of every distinct binary carrying
that name, not just the two originally spotted.

This tool NEVER loads, maps, executes, decompiles, disassembles or type-recovers any
binary. It reads file bytes and parses static PE tables with the repository's existing
producer work/coptersim-compat-20260905/inspect_pe.py (function `inspect`, pefile
fast_load). No vendor material is copied or published; only metadata is recorded.

Writes exactly one artifact, inside this deliverable directory:
    raw/n1-pe-templates.json

Run:  python -B validation/coordination/ds-dll-abi-n1n2-20260913-01/n1_pe_templates_readonly.py
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ anywhere, incl. under work/

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRODUCER = REPO / "work" / "coptersim-compat-20260905" / "inspect_pe.py"
OUT = HERE / "raw" / "n1-pe-templates.json"

ENUMERATION_ROOT = Path("E:/rflysimtools")
ENUMERATED_FILENAME = "Exp1_MinModelTemp.dll"

E0_TEMPLATE = Path(
    "E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp.dll"
)
E1_TEMPLATE = Path(
    "E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e1_MinModelTempLib/Exp1_MinModelTemp.dll"
)
DEPLOYED_EXP1 = Path("E:/rflysimtools/CopterSim/external/model/Exp1_MinModelTemp.dll")
DEPLOYED_MULTI = Path("E:/rflysimtools/CopterSim/external/model/MulticopterNOpx4.dll")

# The four targets that are named by existing repository material or by the vendor
# consumer itself. `recorded_sha256=None` means the value was never on record.
NAMED_TARGETS = [
    {
        "candidate_id": "e0-template-dll",
        "role": "e0 template DLL (the binary the G6 provenance chain is bound to)",
        "path": E0_TEMPLATE,
        "recorded_sha256": "30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b",
        "recorded_in": "validation/model-reference-provenance-20260907/resource-hashes.json lines 13-16; docs/plan/model-reference-provenance.md:17",
        "in_default_16_dll_inventory": False,
    },
    {
        "candidate_id": "e1-template-dll",
        "role": "e1 template DLL (e1_MinModelTempLib)",
        "path": E1_TEMPLATE,
        "recorded_sha256": None,
        "recorded_in": "none - c7 records that the e1 export-name list had no path/size/SHA256",
        "in_default_16_dll_inventory": False,
    },
    {
        "candidate_id": "deployed-model-dir-exp1",
        "role": "deployed copy of the same filename in the CopterSim model directory (c5 second binary)",
        "path": DEPLOYED_EXP1,
        "recorded_sha256": "8134aab646adda098b7c98a4daa17278dbed7a626a1811e18ed1a88288fb6a46",
        "recorded_in": "validation/coordination/ds-dll-abi-evidence-20260913-01/audit.json c5-exp1-two-binaries",
        "in_default_16_dll_inventory": True,
    },
    {
        "candidate_id": "consumer-named-target",
        "role": "the only DLL name hardcoded by the vendor consumer (DllSimCtrlAPI.py:2099); carries a different file name",
        "path": DEPLOYED_MULTI,
        "recorded_sha256": None,
        "recorded_in": "work/coptersim-compat-20260905/evidence/pe-inventory.json 16-DLL inventory, no per-file hash quoted",
        "in_default_16_dll_inventory": True,
    },
]

# Candidates that bear the identical file name Exp1_MinModelTemp.dll.
SAME_FILENAME_GROUP = ("e0-template-dll", "e1-template-dll", "deployed-model-dir-exp1")

LEGACY_OUTPUT_FAMILY = ["DlloutputSensors", "DlloutputGPS", "DlloutModel3DInfo"]
MODERN_OUTPUT_FAMILY = ["DlloutHILSensor30d", "DlloutHILGPS30d", "DlloutVehileInfo60d"]
PROBE_NAMES = [
    "?DllCreatModel@@YAXXZ",
    "DllCreatModel",
    "DllDestroyModel",
    "DllInitPosAngState",
    "DllInitPosAngStat",
    "DllInputDoubCtrls",
    "DllinSIL28d",
    "DllInputSILs",
    "DllInputColls",
    "DllinCollision20d",
    "DllTerrainIn15d",
    "DllInputTerrain",
    "DllInputPWMs",
    "DllGetStep0",
    "Dllstep",
    "DllReInitModel",
    "DllInitGpsPos",
    "DllOutCopterData",
    "DlloutVehileInfo60d",
    "DllGetGpsPos",
    "DllGetInitInputs",
    "DllInCtrlExt",
    "DllInFromEU",
    "DllFaultParamAPI",
    "DllInitParamAPI",
    "DllDynModiParams",
    "DllGetExtToPX4",
    "DllGetExtToUE4",
]
# Probes whose absence is the subject of a recorded contradiction / zero-occurrence claim.
ZERO_OCCURRENCE_PROBES = ["DllInitPosAngStat", "DllInputDoubCtrls"]


def load_producer():
    spec = importlib.util.spec_from_file_location("wksim_inspect_pe", PRODUCER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load read-only PE producer: {PRODUCER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # def-only module; the __main__ guard is not executed
    if not callable(getattr(module, "inspect", None)):
        raise SystemExit("producer has no callable inspect(path)")
    return module


def classify_family(names):
    legacy = sorted(n for n in LEGACY_OUTPUT_FAMILY if n in names)
    modern = sorted(n for n in MODERN_OUTPUT_FAMILY if n in names)
    if legacy and modern:
        family = "legacy+modern (BOTH families in one file)"
    elif legacy:
        family = "legacy-output-name family"
    elif modern:
        family = "modern *30d/*60d family"
    else:
        family = "neither recorded output-name family"
    return {"family": family, "legacy_present": legacy, "modern_present": modern}


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enumerate_same_filename_copies():
    copies = []
    for path in sorted(ENUMERATION_ROOT.rglob(ENUMERATED_FILENAME)):
        if not path.is_file():
            continue
        copies.append({"path": str(path), "size": path.stat().st_size, "sha256": sha256_of(path)})
    return copies


def inspect_record(producer, path):
    record = producer.inspect(path)
    names = [e["name"] for e in record["exports"]]
    dll_names = [n for n in names if n and n.startswith("Dll")]
    record.update(
        {
            "export_count_total": len(record["exports"]),
            "dll_export_names": sorted(dll_names),
            "probed_names_present": sorted(n for n in PROBE_NAMES if n in names),
            "probed_names_absent": sorted(n for n in PROBE_NAMES if n not in names),
            "has_decorated_dllcreatmodel": "?DllCreatModel@@YAXXZ" in names,
            "has_undecorated_dllcreatmodel": "DllCreatModel" in names,
            **classify_family(set(dll_names)),
        }
    )
    return record


def run():
    producer = load_producer()
    result = {
        "schema": "wksim.ds-dll-abi-n1n2.n1-pe-templates.v1",
        "step": "n1",
        "kind": "read-only PE header/import/export/version-table inventory",
        "producer_reused": str(PRODUCER.relative_to(REPO)).replace("\\", "/"),
        "producer_sha256": hashlib.sha256(PRODUCER.read_bytes()).hexdigest(),
        "producer_api_used": "inspect_pe.inspect(path) (pefile fast_load; static tables only)",
        "execution": "none - no DLL/model/exe was loaded, mapped, executed, decompiled or disassembled",
        "named_targets": [],
        "binaries_by_sha256": {},
    }

    def record_binary(path, roles, recorded_sha256=None, recorded_in=None):
        sha = sha256_of(path)
        entry = result["binaries_by_sha256"].get(sha)
        if entry is None:
            entry = inspect_record(producer, path)
            entry["sha256_matches_recorded"] = (
                None if recorded_sha256 is None else sha == recorded_sha256
            )
            entry["recorded_sha256"] = recorded_sha256
            entry["recorded_in"] = recorded_in
            entry["roles"] = []
            entry["paths"] = []
            result["binaries_by_sha256"][sha] = entry
        entry["paths"].append(str(path))
        entry["roles"].extend(r for r in roles if r not in entry["roles"])
        return entry

    for candidate in NAMED_TARGETS:
        path = candidate["path"]
        if not path.exists():
            result["named_targets"].append(
                dict(candidate, path=str(path), present=False, note="path absent on this machine")
            )
            continue
        entry = record_binary(
            path,
            [candidate["candidate_id"]],
            candidate["recorded_sha256"],
            candidate["recorded_in"],
        )
        result["named_targets"].append(
            {
                "candidate_id": candidate["candidate_id"],
                "role": candidate["role"],
                "path": str(path),
                "present": True,
                "size": entry["size"],
                "sha256": entry["sha256"],
                "machine": entry["machine"],
                "family": entry["family"],
                "dll_export_names": entry["dll_export_names"],
                "sha256_matches_recorded": entry["sha256_matches_recorded"],
                "recorded_sha256": entry["recorded_sha256"],
                "recorded_in": entry["recorded_in"],
                "in_default_16_dll_inventory": candidate["in_default_16_dll_inventory"],
            }
        )

    # Enumerate every copy of the shared file name and inspect each distinct binary once.
    copies = enumerate_same_filename_copies()
    for copy in copies:
        path = Path(copy["path"])
        record_binary(path, ["same-filename-copy"])
    result["same_filename_enumeration"] = {
        "root": str(ENUMERATION_ROOT),
        "filename": ENUMERATED_FILENAME,
        "copy_count": len(copies),
        "distinct_binaries": len({c["sha256"] for c in copies}),
        "copies": copies,
        "copies_not_previously_on_record": [
            c
            for c in copies
            if c["sha256"]
            not in {
                "30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b",
                "8134aab646adda098b7c98a4daa17278dbed7a626a1811e18ed1a88288fb6a46",
            }
        ],
    }

    # Cross-binary identity facts, computed rather than asserted.
    same_name_entries = [
        e
        for e in result["binaries_by_sha256"].values()
        if any(r in e["roles"] for r in SAME_FILENAME_GROUP) or "same-filename-copy" in e["roles"]
    ]
    result["same_filename_identity"] = {
        "shared_filename": ENUMERATED_FILENAME,
        "distinct_binaries": len(same_name_entries),
        "distinct_dll_export_name_sets": len({tuple(e["dll_export_names"]) for e in same_name_entries}),
        "distinct_output_families": sorted({e["family"] for e in same_name_entries}),
        "sha256_to_export_names": {
            e["sha256"]: e["dll_export_names"] for e in sorted(same_name_entries, key=lambda x: x["sha256"])
        },
        "members": [
            {
                "sha256": e["sha256"],
                "size": e["size"],
                "family": e["family"],
                "dll_export_count": len(e["dll_export_names"]),
                "roles": e["roles"],
                "paths": e["paths"],
            }
            for e in sorted(same_name_entries, key=lambda x: x["sha256"])
        ],
    }
    templates = [t for t in result["named_targets"] if t["candidate_id"] in ("e0-template-dll", "e1-template-dll")]
    if len(templates) == 2:
        result["template_export_set_comparison"] = {
            "e0_sha256": templates[0]["sha256"],
            "e1_sha256": templates[1]["sha256"],
            "export_name_sets_identical": sorted(templates[0]["dll_export_names"])
            == sorted(templates[1]["dll_export_names"]),
            "size_delta_e1_minus_e0": templates[1]["size"] - templates[0]["size"],
        }

    # The zero-occurrence re-check, over every inspected binary (named + enumerated).
    inspected = list(result["binaries_by_sha256"].values())
    result["zero_occurrence_recheck"] = {
        "binaries_inspected": len(inspected),
        "probe_verdicts": {
            probe: {
                "present_in_binaries": sorted(
                    e["sha256"] for e in inspected if probe in e["probed_names_present"]
                ),
                "absent_from_binaries": sorted(
                    e["sha256"] for e in inspected if probe in e["probed_names_absent"]
                ),
                "distinct_binaries_present": sum(
                    1 for e in inspected if probe in e["probed_names_present"]
                ),
            }
            for probe in ZERO_OCCURRENCE_PROBES
        },
        "output_family_coexistence": {
            "binaries_with_both_legacy_and_modern_output_names": sorted(
                e["sha256"] for e in inspected if e["legacy_present"] and e["modern_present"]
            ),
            "binaries_with_legacy_only": sorted(
                e["sha256"] for e in inspected if e["legacy_present"] and not e["modern_present"]
            ),
            "binaries_with_modern_only": sorted(
                e["sha256"] for e in inspected if e["modern_present"] and not e["legacy_present"]
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert json.loads(OUT.read_text(encoding="utf-8")) == result
    print(
        json.dumps(
            {
                "artifact": str(OUT.relative_to(REPO)).replace("\\", "/"),
                "named_targets": [
                    {
                        "id": t["candidate_id"],
                        "size": t.get("size"),
                        "sha256": t.get("sha256"),
                        "machine": t.get("machine"),
                        "matches_recorded": t.get("sha256_matches_recorded"),
                        "family": t.get("family"),
                        "dll_exports": t.get("dll_export_names"),
                    }
                    for t in result["named_targets"]
                ],
                "enumeration": {
                    "copy_count": result["same_filename_enumeration"]["copy_count"],
                    "distinct_binaries": result["same_filename_enumeration"]["distinct_binaries"],
                    "distinct_export_name_sets": result["same_filename_identity"]["distinct_dll_export_name_sets"],
                    "families": result["same_filename_identity"]["distinct_output_families"],
                    "new_copies_not_on_record": [
                        c["path"] for c in result["same_filename_enumeration"]["copies_not_previously_on_record"]
                    ],
                },
                "zero_occurrence_recheck": result["zero_occurrence_recheck"],
                "template_export_set_comparison": result.get("template_export_set_comparison"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
