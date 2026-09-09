"""Read-only #55 coverage audit. Run from the wksim root. No flight or output writes."""
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path.cwd()
CASE = Path(__file__).resolve().parent
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
data = read(ROOT / "docs/plan/full-followup-tickets.json")
ledger = read(ROOT / "docs/plan/full-remaining-ledger.json")
published = read(CASE / "input-published-issues.json")
readbacks = {x["number"]: x for x in read(CASE / "issued-readback.json")}
parents = {x["number"]: x for x in read(CASE / "parent-evidence.json")}
known = {x["number"]: x for x in read(CASE / "issues-before.json")}
known.update(readbacks)
original_coverage = (CASE / "input-coverage.md").read_text(encoding="utf-8")
source_spec = (ROOT / "docs/plan/full-migration-spec.md").read_text(encoding="utf-8")
source_expansion = (CASE / "input-expansion.md").read_text(encoding="utf-8")
current_expansion = (ROOT / "docs/plan/full-scope-expansion.md").read_text(encoding="utf-8")
current_coverage = (ROOT / "docs/plan/requirement-coverage.md").read_text(encoding="utf-8")

def validate(value):
    assert value["full_complete"] is False
    entries = value["entries"]
    ids = [e["id"] for e in entries]
    expected = [f"{prefix}-{i:02d}" for prefix, count in
                (("US", 48), ("SIM", 12), ("COMM", 7), ("MODEL", 16), ("OPS", 13))
                for i in range(1, count + 1)]
    assert len(ids) == len(set(ids)) == 96 and set(ids) == set(expected)
    originals = {e["id"]: e for e in ledger["entries"]}
    story_lines = re.findall(r"(?m)^(\d+)\. (作为.+)$", source_spec)
    assert len(story_lines) == 48
    stories = {f"US-{int(n):02d}": text for n, text in story_lines}
    pub = {p["local_id"]: p["number"] for p in published["issues"]}
    for e in entries:
        old = originals[e["id"]]
        assert e["original_text"] == old["original_text"]
        assert e["source"] == old["source"]
        assert e["status"] in {"evidenced", "implemented", "blocked", "not-implemented"}
        assert e["full_complete"] is False and e["gap_detail"] and e["owners"]
        assert e["followup_ids"] and all(n in known for n in e["followup_ids"])
        assert 55 not in e["followup_ids"], "self dependency"
        assert f'| {e["id"]} | {e["status"]} |' in current_coverage
        if e["id"].startswith("US"):
            assert stories[e["id"]] == e["original_text"]
            n = int(e["id"][3:])
            line = next(x for x in original_coverage.splitlines() if x.startswith(f"| {n} |"))
            owners = list(dict.fromkeys(pub[int(x)] for x in re.findall(r"tickets/(\d+)-", line))) or [1]
            if n == 32:
                owners = [5, 41]  # explicit approved MATLAB decision + actual bridge AC
            assert e["owners"] == owners, f"story/issue ordinal confusion: {e['id']}"
        else:
            assert e["source"]["markdown"] in source_expansion
            assert e["source"]["markdown"] in current_expansion
            assert f'| {e["id"]} | {e["status"]} |' in current_expansion
        for ref in e["corrected_parent_references"]:
            assert ref["number"] in known
            assert ref["state"] == known[ref["number"]]["state"]
        for evidence in e["evidence"]:
            source = parents[evidence["issue"]]
            assert evidence["issue_state"] == source["state"]
            assert all(c["url"] in [x["url"] for x in source["comments"]] for c in evidence["comments"])
            assert (ROOT / evidence["snapshot"]).is_file()
            if evidence["report"]:
                assert (ROOT / evidence["report"]).is_file(), evidence["report"]
    by_id = {e["id"]: e for e in entries}
    assert by_id["COMM-03"]["owners"] == [1, 42, 43]
    assert by_id["COMM-04"]["owners"] == [1]
    assert by_id["COMM-07"]["owners"] == [1]
    assert by_id["MODEL-02"]["followup_ids"] == [65, 66, 67, 68, 69]
    assert 59 in by_id["MODEL-01"]["followup_ids"]
    assert by_id["SIM-11"]["status"] != "blocked"
    assert [g["id"] for g in value["gates"]] == [f"G{i}" for i in range(7)]
    assert all(g["status"] == "preserved-not-complete" for g in value["gates"])
    assert readbacks[54]["state"] == "CLOSED"
    output_paths = []
    for d in value["definitions"]:
        live = readbacks[d["number"]]
        assert live["state"] == "OPEN" and live["title"] == d["title"]
        body = (CASE / "bodies" / (d["key"] + ".md")).read_text(encoding="utf-8").strip()
        assert live["body"].strip() == body
        assert f"full-followup:{d['key']}:from-55:v1" in body
        assert d["type"] == "expert-definition"
        assert len(d["write_scope"]) == 2
        assert all(p in body for p in d["write_scope"])
        output_paths.extend(d["write_scope"])
        assert all(d["number"] in by_id[row]["followup_ids"] for row in d["row_ids"])
    assert len(value["definitions"]) == 43
    assert len(output_paths) == len(set(output_paths))

validate(data)
mutations = {
    "missing_row": lambda d: d["entries"].pop(),
    "duplicate_row": lambda d: d["entries"].append(copy.deepcopy(d["entries"][0])),
    "wrong_story_parent": lambda d: d["entries"][12].update(owners=[23]),
    "fake_followup": lambda d: d["entries"][0].update(followup_ids=[999999]),
    "changed_source": lambda d: d["entries"][0].update(original_text="changed"),
    "false_full_complete": lambda d: d.update(full_complete=True),
    "mismatched_remote_title": lambda d: d["definitions"][0].update(title="wrong"),
    "false_g6": lambda d: d["gates"][6].update(status="complete"),
}
rejected = []
for name, mutate in mutations.items():
    candidate = copy.deepcopy(data)
    mutate(candidate)
    try:
        validate(candidate)
    except AssertionError:
        rejected.append(name)
    else:
        raise AssertionError(f"mutation not rejected: {name}")

inputs = read(CASE / "input-hashes.json")
unchanged = []
for item in inputs:
    path = Path(item["Path"])
    if path.name not in {"full-scope-expansion.md", "requirement-coverage.md"}:
        assert sha(path).upper() == item["Hash"]
        unchanged.append(path.name)
paths = set()
for e in data["entries"]:
    paths.add(e["source"]["file"])
    for ev in e["evidence"]:
        if ev["report"]:
            paths.add(ev["report"])
paths.update({"docs/plan/full-followup-tickets.json", "docs/plan/requirement-coverage.md",
              "docs/plan/full-scope-expansion.md", "docs/plan/full-remaining-ledger.json",
              "docs/plan/full-remaining-ledger.md"})
counts = {s: sum(e["status"] == s for e in data["entries"]) for s in data["status_semantics"]}
print(json.dumps({"status": "pass", "rows": 96, "classification": counts,
                  "new_issues": 43, "remote_bodies_verified": 43,
                  "negative_mutations_rejected": rejected, "unchanged_inputs": unchanged,
                  "hashes": {p: sha(ROOT / p) for p in sorted(paths)},
                  "scope": "planning/source/reference audit only; no physics, flight, Full or G0-G6 acceptance"},
                 ensure_ascii=False, indent=2))
