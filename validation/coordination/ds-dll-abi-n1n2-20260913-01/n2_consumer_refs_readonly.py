"""n2: precise line-numbered consumer-side reference record for the vendor ctypes
consumer E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py.

Read-only text analysis. It re-reads the consumer, verifies the file SHA256 against the
already-recorded value, byte-compares a fresh re-read of lines 1234-1307 against the
excerpt already on record in validation/model-reference-provenance-20260907/
sdk-wrapper-evidence.json, and then records ONLY the adjacent ranges that were not on
record. The already-recorded block is verified by hash instead of being copied again.

It also records, in a clearly separated supplementary section, the sample-side binding
for the one experiment directory whose name matches the unresolved zero-occurrence symbol
DllInputDoubCtrls. That half of the c3 resolution requirement ("the sample's actual
dll_name argument") is not consumer-side text, so it is kept separate and labelled.

This tool records consumer-side INTENT and target identity only. Consumer material is
never ABI authority; no ABI, calling convention, element width or unit is inferred here.

Writes exactly one artifact, inside this deliverable directory:
    raw/n2-consumer-refs.json

Run:  python -B validation/coordination/ds-dll-abi-n1n2-20260913-01/n2_consumer_refs_readonly.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CONSUMER = Path("E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py")
CONSUMER_RECORDED_SHA256 = "0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420"
PREDECESSOR_EXCERPT = (
    REPO / "validation" / "model-reference-provenance-20260907" / "sdk-wrapper-evidence.json"
)
PREDECESSOR_EXCERPT_SHA256 = "bc0b07ab00455ff6a8aefea1e363077f577590d2d9c8c4a6674746a14b113d60"
OUT = HERE / "raw" / "n2-consumer-refs.json"

# Supplementary sample-side probes: the sample the predecessor audit cited, and the
# ApiExps directory whose name matches the unresolved DllInputDoubCtrls zero-occurrence.
SAMPLE_PROBES = [
    {
        "probe_id": "cited-sample-model-load-30100",
        "why": "the sample the predecessor audit's c3 evidence cites (lunar-57 summary.md:18 / abi-facts.json)",
        "dir": Path(
            "E:/rflysimtools/RflySimAPIs/4.RflySimModel/0.ApiExps/12.DllModelImport/"
            "9.ModelLoadCopterSim30100Python"
        ),
        "script": "DllSimCtrlAPITest.py",
        "batch": "CopterSimDllSILRun.bat",
        "sibling_dll": "MulticopterNOpx4.dll",
    },
    {
        "probe_id": "api-exps-sendInDoubCtrls",
        "why": "the directory literally named after the unresolved DllInputDoubCtrls consumer path",
        "dir": Path(
            "E:/rflysimtools/RflySimAPIs/4.RflySimModel/0.ApiExps/11.inSILAPI/3.inSIL28d/2.sendInDoubCtrls"
        ),
        "script": "inSIL28dTest.py",
        "batch": "Exp1_MinModelTemp.bat",
        "sibling_dll": "Exp1_MinModelTemp.dll",
    },
]

SCRIPT_BINDING_TOKEN = re.compile(r"DllSimCtrlAPI\.|^\s*import\s+DllSimCtrlAPI|dll\.")

PRIOR_WINDOW = (1234, 1307)
CONSTRUCTOR_CONFIG_WINDOW = (1228, 1326)

# Adjacent ranges that were NOT covered by the recorded excerpt (1234-1307).
ADJACENT_RANGES = [
    (143, 180, "DllSimCtrlAPI-UDP-side-class-and-__init__"),
    (348, 384, "DllSimCtrlAPI-sendInDoubCtrls-UDP-sender"),
    (1162, 1176, "ModelLoad-class-and-__init__-signature"),
    (1191, 1222, "target-DLL-name-resolution-per-copter-copy-and-load-call"),
    (1327, 1327, "constructor-tail-calls-CreateVehicle"),
    (1342, 1388, "CreateVehicle-init-and-first-step-call-order"),
    (1392, 1420, "Updata3Doutput-output-reads-and-terrain-input"),
    (1564, 1580, "fillList-length-coercion-used-by-every-argtypes-wrapper"),
    (1611, 1650, "AutUpdateLoop-step-driver"),
    (1691, 1788, "Recv30100Loop-input-dispatch"),
    (1793, 1981, "wrapper-methods-and-step-accessors"),
    (2000, 2030, "output-read-wrappers"),
    (2038, 2093, "control-encoders-calling-DllInputDoubCtrls"),
    (2096, 2103, "MultiCopterDll-hardcoded-default-target"),
]

# Only lines carrying one of these tokens are quoted verbatim from the adjacent ranges.
BINDING_TOKEN = re.compile(
    r"hasattr\(self\.dll|"
    r"self\.dll\.|"
    r"\.argtypes|"
    r"\.restype|"
    r"^\s*def\s+Dll|"
    r"^\s*def\s+sendInDoubCtrls|"
    r"^\s*class\s+DllSimCtrlAPI|"
    r"ctypes\.|"
    r"dll_full_name|"
    r"PSP_PATH|"
    r"psp_path|"
    r"CDLL|WinDLL|LoadLibrary|"
    r"\.dll|"
    r"shutil\.copy|"
    r"DLLModel"
)

HASATTR_RE = re.compile(r'hasattr\(self\.dll,\s*"([A-Za-z0-9_]+)"\)')
SELF_DLL_RE = re.compile(r"self\.dll\.([A-Za-z0-9_]+)")
DEF_RE = re.compile(r"^\s*def\s+([A-Za-z0-9_]+)\s*\(")
RAW_TOKEN_RE = re.compile(r"\b(Dll[A-Za-z0-9_]+)\b")
DLL_LITERAL_RE = re.compile(r"['\"]([^'\"]*\.dll)['\"]")
CTYPE_RE = re.compile(r"ctypes\.(c_[A-Za-z0-9_]+)\s*\*\s*(\d+)")

# Class/type names that match the Dll* token shape but are not export symbols.
NON_SYMBOL_TOKENS = {"DllSimCtrlAPI", "DllModel"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def verify_file(path, expected_sha256, label):
    if not path.exists():
        raise SystemExit(f"{label} absent: {path}")
    data = path.read_bytes()
    sha = sha256_bytes(data)
    if expected_sha256 is not None and sha != expected_sha256:
        raise SystemExit(f"{label} drifted: recorded {expected_sha256}, live {sha}")
    return data, sha


def classify(line_text, symbol):
    if line_text.strip().startswith("#"):
        return ["comment-mention"]
    kinds = []
    if HASATTR_RE.search(line_text) and f'"{symbol}"' in line_text:
        kinds.append("hasattr-guard")
    if f"self.dll.{symbol}" in line_text:
        if ".argtypes" in line_text:
            kinds.append("argtypes-assignment")
        elif ".restype" in line_text:
            kinds.append("restype-assignment")
        elif HASATTR_RE.search(line_text):
            kinds.append("guarded-attribute-access")
        else:
            kinds.append("passthrough-call-or-access")
    m = DEF_RE.match(line_text)
    if m and m.group(1) == symbol:
        kinds.append("wrapper-def")
    if not kinds:
        kinds.append("mention")
    return kinds


def analyse_constructor_window(lines):
    """Bind every constructor configuration statement to its guard, its symbol and its
    declared ctypes shape; flag guards that guard a different name than they access."""
    lo, hi = CONSTRUCTOR_CONFIG_WINDOW
    configured = {}
    guard_mismatches = []
    argtypes_blocks = {}
    restype_lines = {}
    current_guard = None

    for n in range(lo, hi + 1):
        text = lines[n - 1]
        stripped = text.strip()
        guard = HASATTR_RE.search(text)
        access = SELF_DLL_RE.search(text)

        if not stripped or stripped.startswith("#"):
            continue  # blank/comment lines never close a guard block

        if guard:
            current_guard = {"name": guard.group(1), "line": n}
            configured.setdefault(guard.group(1), []).append(
                {"line": n, "kind": "guard", "guard": guard.group(1), "text": stripped}
            )
            continue

        if access:
            symbol = access.group(1)
            if ".argtypes" in text:
                kind = "argtypes"
            elif ".restype" in text:
                kind = "restype"
            else:
                kind = "attribute-access"
            entry = {
                "line": n,
                "kind": kind,
                "guard": current_guard["name"] if current_guard else None,
                "guard_line": current_guard["line"] if current_guard else None,
                "text": stripped,
            }
            configured.setdefault(symbol, []).append(entry)
            if guard is None and current_guard and current_guard["name"] != symbol:
                guard_mismatches.append(
                    {
                        "line": n,
                        "guard_name": current_guard["name"],
                        "guard_line": current_guard["line"],
                        "accessed_name": symbol,
                        "kind": kind,
                        "text": stripped,
                    }
                )
            if kind == "argtypes":
                block = [{"line": n, "text": stripped}]
                for m in range(n + 1, hi + 1):
                    inner = lines[m - 1]
                    block.append({"line": m, "text": inner.strip()})
                    if inner.strip().startswith("]"):
                        break
                declared = []
                for item in block:
                    match = CTYPE_RE.search(item["text"])
                    if match:
                        declared.append(
                            {"line": item["line"], "ctype": match.group(1), "count": int(match.group(2))}
                        )
                argtypes_blocks.setdefault(symbol, []).append(
                    {
                        "start_line": n,
                        "end_line": block[-1]["line"],
                        "guard": current_guard["name"] if current_guard else None,
                        "declared": declared,
                        "block": block,
                    }
                )
            if kind == "restype":
                restype_lines.setdefault(symbol, []).append(
                    {
                        "line": n,
                        "guard": current_guard["name"] if current_guard else None,
                        "text": stripped,
                    }
                )
            continue

        # Any other substantive statement ends the preceding guard block.
        current_guard = None

    # A symbol whose every configuration entry sits under a guard naming a *different*
    # symbol can never be configured by any binary that lacks that other name.
    unreachable = {}
    for symbol, entries in configured.items():
        if all(e["kind"] == "guard" for e in entries):
            continue
        if any(e.get("guard") in (None, symbol) for e in entries):
            continue
        unreachable[symbol] = {
            "guarded_only_by": sorted({e["guard"] for e in entries if e.get("guard")}),
            "entries": entries,
        }

    repeated = {
        symbol: [b["start_line"] for b in blocks]
        for symbol, blocks in argtypes_blocks.items()
        if len(blocks) > 1
    }
    return {
        "window": {"first_line": lo, "last_line": hi},
        "configured_symbols": configured,
        "guard_name_access_name_mismatches": guard_mismatches,
        "declared_argtypes_blocks": argtypes_blocks,
        "declared_restype_lines": restype_lines,
        "symbols_with_repeated_argtypes_declarations": repeated,
        "symbols_configured_only_under_foreign_guard": unreachable,
    }


def probe_sample_side():
    result = {
        "why": (
            "c3's resolution requirement names two halves: the sample's actual dll_name argument and the "
            "export table of that exact binary. The export tables are in n1; this section records the "
            "sample-side half, including the sample the predecessor audit actually cited."
        ),
        "executed": False,
        "probes": [],
    }
    for probe in SAMPLE_PROBES:
        entry = {"probe_id": probe["probe_id"], "why": probe["why"], "directory": str(probe["dir"])}
        script = probe["dir"] / probe["script"]
        batch = probe["dir"] / probe["batch"]
        sibling = probe["dir"] / probe["sibling_dll"]

        if script.exists():
            data = script.read_bytes()
            text = data.decode("utf-8", "replace")
            entry["script"] = {
                "path": str(script),
                "size": len(data),
                "sha256": sha256_bytes(data),
                "line_count": len(text.splitlines()),
                "binding_lines": [
                    {"line": i, "text": line.rstrip(), "commented_out": line.lstrip().startswith("#")}
                    for i, line in enumerate(text.splitlines(), start=1)
                    if SCRIPT_BINDING_TOKEN.search(line)
                ],
                "instantiates_consumer_class": sorted(
                    {
                        m.group(1)
                        for line in text.splitlines()
                        for m in [re.search(r"DllSimCtrlAPI\.([A-Za-z0-9_]+)\(", line)]
                        if m
                    }
                ),
                "references_model_load": "ModelLoad" in text,
                "references_ctypes_dll_object": bool(re.search(r"self\.dll|\.dll\.", text)),
            }
        else:
            entry["script"] = {"path": str(script), "present": False}

        if batch.exists():
            data = batch.read_bytes()
            text = data.decode("utf-8", "replace")
            entry["batch"] = {
                "path": str(batch),
                "size": len(data),
                "sha256": sha256_bytes(data),
                "dllmodel_lines": [
                    {"line": i, "text": line.rstrip()}
                    for i, line in enumerate(text.splitlines(), start=1)
                    if "DLLModel" in line
                ],
            }
        else:
            entry["batch"] = {"path": str(batch), "present": False}

        if sibling.exists():
            data = sibling.read_bytes()
            entry["sibling_dll"] = {
                "path": str(sibling),
                "name": probe["sibling_dll"],
                "size": len(data),
                "sha256": sha256_bytes(data),
                "pe_inspected_here": False,
                "note": "identity only; the PE export table is read in n1 when the same binary is a named target",
            }
        else:
            entry["sibling_dll"] = {"path": str(sibling), "present": False}
        result["probes"].append(entry)
    return result


def run():
    data, sha = verify_file(CONSUMER, CONSUMER_RECORDED_SHA256, "vendor consumer")
    lines = data.decode("utf-8").splitlines()
    pred_text = verify_file(PREDECESSOR_EXCERPT, PREDECESSOR_EXCERPT_SHA256, "predecessor excerpt")[0]
    pred = json.loads(pred_text.decode("utf-8"))
    recorded = pred["lines_1234_1307"]
    start, end = PRIOR_WINDOW
    fresh_block = [{"line": n, "text": lines[n - 1]} for n in range(start, end + 1)]

    # 1. Verify the already-recorded block instead of copying it a second time.
    prior_verification = {
        "recorded_in": "validation/model-reference-provenance-20260907/sdk-wrapper-evidence.json lines_1234_1307",
        "recorded_artifact_sha256": PREDECESSOR_EXCERPT_SHA256,
        "window": {"first_line": start, "last_line": end, "line_count": len(recorded)},
        "fresh_reread_equals_recorded": fresh_block == recorded,
        "fresh_block_sha256": sha256_bytes(json.dumps(fresh_block, ensure_ascii=False).encode("utf-8")),
        "recorded_block_sha256": sha256_bytes(json.dumps(recorded, ensure_ascii=False).encode("utf-8")),
        "text_not_duplicated_here": True,
    }
    if not prior_verification["fresh_reread_equals_recorded"]:
        diff = [
            {"line": a["line"], "fresh": a["text"], "recorded": b["text"]}
            for a, b in zip(fresh_block, recorded, strict=False)
            if a != b
        ]
        prior_verification["differences"] = diff[:20]
        prior_verification["difference_count"] = len(diff)

    # 2. Full per-symbol reference table over the whole file (line numbers + kind).
    table = {}
    for idx, text in enumerate(lines, start=1):
        if not BINDING_TOKEN.search(text) and "Dll" not in text:
            continue
        for symbol in set(RAW_TOKEN_RE.findall(text)) | set(HASATTR_RE.findall(text)) | set(
            SELF_DLL_RE.findall(text)
        ):
            if symbol in NON_SYMBOL_TOKENS:
                continue
            table.setdefault(symbol, [])
            for kind in classify(text, symbol):
                entry = {"line": idx, "kind": kind}
                if entry not in table[symbol]:
                    table[symbol].append(entry)
    for symbol in table:
        table[symbol].sort(key=lambda item: (item["line"], item["kind"]))

    code_referenced = sorted(
        s
        for s, refs in table.items()
        if any(
            r["kind"]
            in {
                "argtypes-assignment",
                "restype-assignment",
                "guarded-attribute-access",
                "passthrough-call-or-access",
                "wrapper-def",
            }
            for r in refs
        )
    )

    config = analyse_constructor_window(lines)

    # Missing / unreachable initialisation branches, bound to exact lines.
    wrapper_symbols = sorted(
        s for s, refs in table.items() if any(r["kind"] == "wrapper-def" for r in refs)
    )
    configured_with_shape = set(config["declared_argtypes_blocks"]) | set(config["declared_restype_lines"])
    missing_initialisation = {
        "wrapper_symbols_with_no_argtypes_and_no_restype": sorted(
            s for s in wrapper_symbols if s not in configured_with_shape
        ),
        "consumer_code_referenced_symbols_without_any_constructor_configuration": sorted(
            s
            for s in code_referenced
            if s not in set(config["configured_symbols"]) and s not in configured_with_shape
        ),
        "symbols_whose_only_configuration_sits_under_a_foreign_guard": sorted(
            config["symbols_configured_only_under_foreign_guard"]
        ),
        "unreachable_argtypes_blocks": {
            symbol: [
                {"start_line": b["start_line"], "end_line": b["end_line"], "guard_name": b["guard"]}
                for b in blocks
            ]
            for symbol, blocks in config["declared_argtypes_blocks"].items()
            if symbol in config["symbols_configured_only_under_foreign_guard"]
        },
    }

    # 3. Target-DLL identity: how the binary is chosen and mirrored.
    identity_lines = [
        {"line": idx, "text": text.strip()}
        for idx, text in enumerate(lines, start=1)
        if re.search(r"\.dll|dll_full_name|PSP_PATH|psp_path|CDLL|WinDLL|shutil\.copy", text)
    ]
    literals = [
        {"line": idx, "literal": m.group(1)}
        for idx, text in enumerate(lines, start=1)
        for m in [DLL_LITERAL_RE.search(text)]
        if m
    ]
    loader_call_lines = [
        {"line": idx, "text": text.strip()}
        for idx, text in enumerate(lines, start=1)
        if re.search(r"CDLL\(|WinDLL\(|LoadLibrary", text)
    ]

    # 4. Minimal verbatim key lines from the adjacent ranges.
    adjacent = {}
    for lo, hi, label in ADJACENT_RANGES:
        key_lines = [
            {"line": n, "text": lines[n - 1].rstrip()}
            for n in range(lo, hi + 1)
            if BINDING_TOKEN.search(lines[n - 1]) or "Dll" in lines[n - 1]
        ]
        adjacent[label] = {
            "range": {"first_line": lo, "last_line": hi},
            "key_lines": key_lines,
            "key_line_count": len(key_lines),
        }

    result = {
        "schema": "wksim.ds-dll-abi-n1n2.n2-consumer-refs.v1",
        "step": "n2",
        "kind": "read-only consumer-side line-numbered reference record",
        "authority_caveat": "consumer-side ctypes declarations are recorded as intent, never as ABI authority",
        "consumer": {
            "path": str(CONSUMER),
            "size": len(data),
            "line_count": len(lines),
            "sha256": sha,
            "recorded_sha256": CONSUMER_RECORDED_SHA256,
            "sha256_matches_recorded": sha == CONSUMER_RECORDED_SHA256,
        },
        "prior_excerpt_verification": prior_verification,
        "symbol_reference_table": table,
        "symbols_with_code_references": code_referenced,
        "constructor_configuration": config,
        "missing_initialisation_branches": missing_initialisation,
        "target_dll_identity": {
            "identity_lines": identity_lines,
            "dll_path_literals": literals,
            "dll_loader_call_lines": loader_call_lines,
            "dll_loader_mechanism": (
                "ctypes.CDLL" if any("CDLL" in item["text"] for item in loader_call_lines) else "none found"
            ),
        },
        "adjacent_excerpts": adjacent,
        "adjacent_ranges_covered": [label for _, _, label in ADJACENT_RANGES],
        "supplementary_sample_side_probe": probe_sample_side(),
        "limits": "Text-only. The consumer is not ABI authority; no ABI, calling convention, element width or unit is inferred from it.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert json.loads(OUT.read_text(encoding="utf-8")) == result
    print(
        json.dumps(
            {
                "artifact": str(OUT.relative_to(REPO)).replace("\\", "/"),
                "consumer_sha256_matches": result["consumer"]["sha256_matches_recorded"],
                "prior_excerpt_verified_equal": prior_verification["fresh_reread_equals_recorded"],
                "symbols_with_code_references": code_referenced,
                "guard_mismatches": config["guard_name_access_name_mismatches"],
                "repeated_argtypes": config["symbols_with_repeated_argtypes_declarations"],
                "unreachable_config": {
                    k: v["guarded_only_by"] for k, v in config["symbols_configured_only_under_foreign_guard"].items()
                },
                "dll_literals": literals,
                "dll_loader": result["target_dll_identity"]["dll_loader_mechanism"],
                "missing_initialisation_branches": missing_initialisation,
                "sample_probes": [
                    {
                        "probe_id": p["probe_id"],
                        "script": p["script"].get("sha256"),
                        "instantiates": p["script"].get("instantiates_consumer_class"),
                        "sibling_dll": {k: p["sibling_dll"].get(k) for k in ("name", "size", "sha256")},
                        "dllmodel": [
                            item["text"] for item in p["batch"].get("dllmodel_lines", []) if "set DLLModel" in item["text"]
                        ],
                    }
                    for p in result["supplementary_sample_side_probe"]["probes"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
