"""Independent assessment of caching a module-scope JSONEncoder in encoded().

DeepSeek B's proposal: replace ``json.dumps(value, separators=(',', ':'),
allow_nan=False)`` inside worker.py ``encoded()`` with a single module-scope
``json.JSONEncoder(separators=(',', ':'), allow_nan=False).encode(value)``.

This script NEVER imports worker.py or Model.  It AST-extracts the real
``encoded`` function from the SHA-pinned archived snapshot, builds the
candidate next to it, and compares bytes/exceptions on representative payloads
whose shapes come from the archived source (request frame at
receive_workers, response/extras at _worker_loop); it also checks a shared
encoder under threads and reports a bounded pure-encoding timing distribution
(median/p95/p99/min - no upper-bound claims).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import statistics
import sys
import threading
import time
from pathlib import Path

EXPECTED_WORKER_SHA256 = \
    "0becd1f3214b53c6169fb61ae010a969fb57a4ccbe26fb3ed3c3652c26ef7fab"
DEFAULT_SOURCE = Path(
    "/root/wksim-release-acceptance-fe3/validation/"
    "joint-public-flight-rfw9nmbb/source__Simulator__wksim_core__worker.py.txt")
TIMING_ITERATIONS = 3000
THREADS = 8
THREAD_ITERATIONS = 500

_CACHED = json.JSONEncoder(separators=(",", ":"), allow_nan=False)


def candidate_encoded(value):
    """DeepSeek B's proposed body, evaluated standalone."""
    return _CACHED.encode(value)


def extract_encoded(source_bytes):
    """Compile only the module-level ``encoded`` function; no module import."""
    tree = ast.parse(source_bytes, filename="worker.py")
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "encoded"]
    if len(functions) != 1:
        raise ValueError("encoded not unique at module level")
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {"json": json, "__builtins__": __builtins__}
    exec(compile(ast.fix_missing_locations(module), "worker.py", "exec"),
         namespace)
    return namespace["encoded"], tree


def call_site_census(tree):
    """Static count of encoded() call sites per enclosing function."""
    census = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = sum(1 for item in ast.walk(node)
                        if isinstance(item, ast.Call)
                        and isinstance(item.func, ast.Name)
                        and item.func.id == "encoded")
            if calls:
                census[node.name] = calls
    return census


EPOCH = "9b18d3d1322749db8e7dfccd7891b885"


def representative_payloads():
    """Shapes per archived source; not captured bytes."""
    request = dict(version=1, epoch=EPOCH, tick=12345,
                   commands=[0.05 * i for i in range(16)])
    request_terrain = dict(version=1, epoch=EPOCH, tick=12346,
                           commands=[0.0] * 16,
                           terrain=dict(height_m=12.5, source="query"))
    response = dict(version=1, epoch=EPOCH, tick=12345,
                    state=[float(i) / 7.0 for i in range(120)])
    initial_response = dict(version=1, epoch=EPOCH, tick=0,
                            state=[0.0] * 120, initial=True)
    extras = dict(commands=request["commands"],
                  input=json.dumps(request) + "\n", request=request)
    extras_terrain = dict(commands=request_terrain["commands"],
                          input=json.dumps(request_terrain) + "\n",
                          request=request_terrain,
                          terrain=request_terrain["terrain"])
    return {
        "request": request,
        "request_terrain": request_terrain,
        "response": response,
        "initial_response": initial_response,
        "extras": extras,
        "extras_terrain": extras_terrain,
        "unicode_fields": dict(version=1, epoch=EPOCH, tick=1,
                               state=[], note="温度µ\u0000末端"),
        "int_keys": {1: "one", 2.5: "two.point.five", True: "bool",
                     None: "null"},
        "nested_empty": dict(version=1, epoch=EPOCH, tick=2, state=[],
                             empty={}, items=[[], [{}]]),
    }


def exception_battery():
    nan_payload = dict(version=1, epoch=EPOCH, tick=3, state=[float("nan")])
    inf_payload = dict(version=1, epoch=EPOCH, tick=3, state=[float("inf")])
    circular = {}
    circular["self"] = circular
    return {"nan_state": nan_payload, "inf_state": inf_payload,
            "circular": circular, "tuple_key": {(1, 2): "tuple-key"}}


def _outcome(function, value):
    try:
        return ("ok", function(value))
    except ValueError as error:
        return ("ValueError", str(error))
    except TypeError as error:
        return ("TypeError", str(error))


def equivalence(real_encoded):
    rows = []
    for name, payload in representative_payloads().items():
        original = _outcome(real_encoded, payload)
        candidate = _outcome(candidate_encoded, payload)
        rows.append(dict(payload=name, original=original[0],
                         candidate=candidate[0],
                         identical=original == candidate))
    for name, payload in exception_battery().items():
        original = _outcome(real_encoded, payload)
        candidate = _outcome(candidate_encoded, payload)
        rows.append(dict(payload=name, original=original[:1],
                         candidate=candidate[:1],
                         identical=original == candidate))
    return rows


def threading_check(real_encoded):
    payload = representative_payloads()["response"]
    expected = real_encoded(payload)
    errors = []

    def hammer():
        for _ in range(THREAD_ITERATIONS):
            if candidate_encoded(payload) != expected:
                errors.append("divergence")

    threads = [threading.Thread(target=hammer) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {"threads": THREADS, "encodes_per_thread": THREAD_ITERATIONS,
            "divergences": len(errors)}


def timing_distribution(real_encoded):
    payload = representative_payloads()["response"]
    result = {}
    for label, function in (("dumps", real_encoded),
                            ("cached_encoder", candidate_encoded)):
        for _ in range(200):  # warmup
            function(payload)
        samples = []
        for _ in range(TIMING_ITERATIONS):
            began = time.perf_counter_ns()
            function(payload)
            samples.append(time.perf_counter_ns() - began)
        ordered = sorted(samples)
        result[label] = dict(
            iterations=TIMING_ITERATIONS,
            min_ns=ordered[0],
            median_ns=statistics.median(ordered),
            p95_ns=ordered[(len(ordered) * 95 // 100) - 1],
            p99_ns=ordered[(len(ordered) * 99 // 100) - 1],
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    source = args.source.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha != EXPECTED_WORKER_SHA256:
        raise SystemExit("source is not the pinned worker snapshot")
    real_encoded, tree = extract_encoded(source)

    result = {
        "schema": "wksim.worker-encoded-cache-review.v1",
        "python": sys.version,
        "source_sha256": source_sha,
        "module_imported": False,
        "call_site_census": call_site_census(tree),
        "equivalence": equivalence(real_encoded),
        "threading": threading_check(real_encoded),
        "timing": timing_distribution(real_encoded),
        "limits": [
            "Payload shapes follow the archived source; they are not captured "
            "bytes from a run.",
            "Timing is a bounded pure-encoding microbenchmark on this host; "
            "min/median/p95/p99 are sample statistics, never upper bounds.",
            "Thread safety conclusion is CPython-3.10-specific: encode() builds "
            "a fresh iterator per call and the encoder holds no mutable state, "
            "matching json's own module-scope _default_encoder pattern.",
        ],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.output.exists():
        raise SystemExit(f"output exists, refusing: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "call_site_census": result["call_site_census"],
        "equivalence_all_identical":
            all(row["identical"] for row in result["equivalence"]),
        "threading": result["threading"],
        "timing": result["timing"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
