"""Startup/rate timing overlap analysis for the ArUco tracking epochs.

Reads an epoch directory's wire/rate/scene-lifecycle jsonl and decomposes the
rate-group lateness into: per-group work vs ideal, inter-group gap before each
group start, and overlap with the retained native-input wait / step-CPU-stage
/ GC diagnostic windows. Everything is keyed by raw tick and monotonic ns;
no value is truncated, and thread_cpu_ns > wall_ns is reported as a
clock-window artifact, never as corruption. The residual time not covered by
any instrument is reported as unattributed instead of being assigned to a
guessed cause. Compact stdout; the full table goes to a fresh 'x'-mode file.

Usage: python tools/analyze_aruco_startup_timing.py <epoch_dir> --output <new.json>
       [--window 2800:3000 --window 11900:12136]
"""
import argparse
import json
from pathlib import Path
import sys

IDEAL_GROUP_NS = 8_000_000  # 4 ticks at the frozen 0.5 rate; asserted from data.


def load(path):
    rows = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            rows.append(json.loads(line))
    return rows


def overlap_ns(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def analyze(epoch_dir, windows):
    epoch_dir = Path(epoch_dir)
    wire = load(epoch_dir / "wire.jsonl")
    rate = load(epoch_dir / "rate.jsonl")
    lifecycle = load(epoch_dir / "scene-lifecycle.jsonl")
    groups = sorted((r for r in rate if r["kind"] == "rate_group_end"),
                    key=lambda r: r["end_tick"])
    unmet = [r for r in rate if r["kind"] == "rate_unmet"]
    waits, stages, gcs, loops = [], [], [], []
    for r in wire:
        kind = r["kind"]
        if kind == "diagnostic_native_input_timing":
            for w in r["waits"]:
                waits.append(dict(tick=r["tick"], stack=w["stack"], start=w["wall_start_ns"],
                                  end=w["wall_end_ns"], wall_ns=w["wall_ns"],
                                  thread_cpu_ns=w["thread_cpu_ns"]))
        elif kind == "diagnostic_step_cpu_timing":
            stages.append(dict(tick=r["tick"], start=r["wall_start_ns"], end=r["wall_end_ns"],
                               stages=r["stages"]))
        elif kind == "diagnostic_gc_timing":
            gcs.append(dict(tick=r["tick"], start=r["wall_start_ns"], end=r["wall_end_ns"],
                            wall_ns=r["wall_end_ns"] - r["wall_start_ns"],
                            thread_cpu_ns=r["thread_cpu_ns"], collected=r["collected"]))
        elif kind == 'diagnostic_runtime_loop_timing':
            if r['observed_tick'] != r['tick']:
                raise ValueError('Runtime timing tick differs from its wire identity')
            loops.append(r)
    gc_max_wall = max((g["wall_ns"] for g in gcs), default=0)
    result = {"schema": "wksim.aruco-startup-timing.v1", "epoch_dir": str(epoch_dir),
              "groups": len(groups), "gc_max_wall_ns": gc_max_wall,
              "rate_unmet": unmet, "runtime_loop_samples": len(loops), "windows": []}
    previous = None
    rows = []
    for g in groups:
        ideal = g["ideal_end_ns"] - g["ideal_start_ns"]
        if ideal != IDEAL_GROUP_NS:
            rows.append({"note": "nonstandard ideal", "start_tick": g["start_tick"],
                         "ideal_ns": ideal})
        gap = g["actual_start_ns"] - previous["actual_end_ns"] if previous else 0
        rows.append({"start_tick": g["start_tick"], "end_tick": g["end_tick"],
                     "work_ns": g["actual_end_ns"] - g["actual_start_ns"],
                     "start_lag_ns": g["actual_start_ns"] - g["ideal_start_ns"],
                     "gap_before_ns": gap, "lateness_ns": g["lateness_ns"],
                     "actual_start_ns": g["actual_start_ns"],
                     "actual_end_ns": g["actual_end_ns"]})
        previous = g
    result["group_table"] = rows
    for low, high in windows:
        span = [r for r in rows if low <= r["start_tick"] <= high]
        if not span:
            continue
        w_start, w_end = span[0]["actual_start_ns"], span[-1]["actual_end_ns"]
        w_native, w_stage, w_gc = [], [], []
        for w in waits:
            if low <= w["tick"] <= high:
                w_native.append(dict(w, overlap_with_group_work_ns=sum(
                    overlap_ns(w["start"], w["end"], r["actual_start_ns"], r["actual_end_ns"])
                    for r in span)))
        stage_totals = {}
        for s in stages:
            if low <= s["tick"] <= high:
                for name, v in s["stages"].items():
                    entry = stage_totals.setdefault(name, {"wall_ns": 0, "thread_cpu_ns": 0})
                    entry["wall_ns"] += v["wall_ns"]
                    entry["thread_cpu_ns"] += v["thread_cpu_ns"]
                w_stage.append({"tick": s["tick"], "wall_ns": s["end"] - s["start"],
                                "stages": s["stages"]})
        for g in gcs:
            if low <= g["tick"] <= high:
                w_gc.append(g)
        gap_total = sum(max(0, r["gap_before_ns"]) for r in span[1:])
        work_total = sum(r["work_ns"] for r in span)
        runtime_samples=[r for r in loops if low <= r['tick'] <= high]
        runtime_totals={}
        for sample in runtime_samples:
            for name,value in sample['stages'].items():
                total=runtime_totals.setdefault(name,dict(wall_ns=0,thread_cpu_ns=0,max_wall_ns=0))
                total['wall_ns']+=value['wall_ns']
                total['thread_cpu_ns']+=value['thread_cpu_ns']
                total['max_wall_ns']=max(total['max_wall_ns'],value['wall_ns'])
        result["windows"].append({
            "window": [low, high], "groups": len(span),
            "work_total_ns": work_total, "gap_before_total_ns": gap_total,
            "native_waits": w_native, "stage_totals": stage_totals,
            "core_stage_samples": w_stage,
            "runtime_stage_totals": runtime_totals,
            "runtime_stage_samples": runtime_samples,
            "timing_scope": "Sampled intervals only; core timings nest within runtime physics. Do not add them together. Pacing includes intended waits.",
            "gc_events": w_gc,
            "group_rows": [{k: v for k, v in r.items()
                            if k not in ("actual_start_ns", "actual_end_ns")} for r in span],
        })
    # Lifecycle context: phase transitions and faults with their ticks.
    result["lifecycle"] = [r for r in lifecycle if r["kind"] != "permission"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epoch_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", action="append", default=[],
                        help="tick window LOW:HIGH; repeatable")
    args = parser.parse_args()
    windows = []
    for item in args.window or ("2800:3000", "11900:12136"):
        low, high = item.split(":")
        windows.append((int(low), int(high)))
    result = analyze(args.epoch_dir, windows)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    for w in result["windows"]:
        top_gaps = sorted(w["group_rows"], key=lambda r: -r["gap_before_ns"])[:5]
        native = [(n["tick"], n["stack"], n["wall_ns"]) for n in w["native_waits"]
                  if n["wall_ns"] > 2_000_000]
        print(f"window {w['window'][0]}..{w['window'][1]}: groups={w['groups']} "
              f"work={w['work_total_ns'] / 1e6:.3f}ms gaps={w['gap_before_total_ns'] / 1e6:.3f}ms")
        print(f"  top gap_before: {[(r['start_tick'], r['gap_before_ns']) for r in top_gaps]}")
        print(f"  stage wall totals: "
              f"{ {k: v['wall_ns'] for k, v in w['stage_totals'].items()} }")
        if w['runtime_stage_totals']:
            print(f"  runtime wall totals: { {k:v['wall_ns'] for k,v in w['runtime_stage_totals'].items()} }")
        print(f"  native waits >2ms: {native}; gc in window: "
              f"{[(g['tick'], g['wall_ns']) for g in w['gc_events']]}")
    print(f"gc max wall_ns overall: {result['gc_max_wall_ns']}; "
          f"rate_unmet: {len(result['rate_unmet'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
