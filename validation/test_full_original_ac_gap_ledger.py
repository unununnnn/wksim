"""Fail-closed offline validation of the Full original-AC gap ledger.

Scope: this suite validates the *captured snapshot* of GitHub Issues #11-#48 held in
``validation/full-original-ac-gap-ledger-snapshot-20260914.json``
together with the ledger derived from it
(``validation/full-original-ac-gap-ledger-20260914.json``) and the plan document
``docs/plan/full-original-ac-gap-ledger-20260914.md``.
The original ignored DeepSeek capture directory is advisory provenance only
and is never imported at test time.

It never touches the network, never calls ``gh``, never imports project code, never
executes a product/native/model/MATLAB/ROS/DDS/SITL/FC/UE/build/flight path, and never
mutates Git. It reads text, computes hashes and compares sets.

Two independent representations of the frozen universe are used, so that no ledger
count is ever its own source of truth:

* Representation A -- the hand-written literal registry ``ISSUE_REGISTRY`` and
  ``BODY_PINS`` below (issue state, checkbox totals, checked counts, body digests).
* Representation B -- the snapshot itself, re-parsed here by a section-scoped
  extractor that walks the Markdown heading structure, plus a flat token scan. The
  two extractors must agree, and A must agree with both.

Model (matters for #20): a body can contain task-list checkboxes *outside* the
``## Acceptance criteria`` section (for example the child-ticket container block at
the top of #20). Every checkbox is parsed and counted as a raw checkbox; only the
checkboxes inside the acceptance section form the **original AC universe**. The
non-AC checkboxes are recorded separately and are never presented as acceptance
criteria.

Exit code 0 = PASS, 1 = at least one check failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "validation" / "full-original-ac-gap-ledger-snapshot-20260914.json"
LEDGER = REPO / "validation" / "full-original-ac-gap-ledger-20260914.json"
PLAN_DOC = REPO / "docs" / "plan" / "full-original-ac-gap-ledger-20260914.md"
EXPECTED_HEAD = "6eafdf9c0b734db07a9fe790c86b409d3468c10b"
EXPECTED_SNAPSHOT_REL = "validation/full-original-ac-gap-ledger-snapshot-20260914.json"
EXPECTED_SNAPSHOT_SHA256 = (
    "c8af0dcef3dfc3a78141d381a9cb307fc5a0a223cc9c2898a5a34fd0ffae1ef4"
)
EXPECTED_ID_FORMAT = (
    "{issue}:{k}, k is 1-based over checkboxes inside the issue's "
    "Acceptance criteria section in body order; non-AC checkboxes use "
    "{issue}:x{ordinal} where ordinal is 1-based over all parsed "
    "checkboxes of the issue"
)
BANNED_IGNORED_UNTRACKED_EVIDENCE = {
    "validation/gcs-handoff-20260909",
    "validation/rgb-lifecycle-20260907-run1",
    "validation/depth-lifecycle-20260908-run1",
}

ISSUE_FIRST = 11
ISSUE_LAST = 48
EXPECTED_ISSUE_COUNT = 38
EXPECTED_ISSUE_SUM = sum(range(ISSUE_FIRST, ISSUE_LAST + 1))  # 1121

# Frozen universe totals (independent literals).
EXPECTED_RAW_CHECKBOXES = 255
EXPECTED_RAW_CHECKED = 40
EXPECTED_AC_TOTAL = 190
EXPECTED_AC_CHECKED = 40
EXPECTED_AC_UNCHECKED = 150
EXPECTED_NON_AC_CHECKBOXES = 65
EXPECTED_NON_AC_ISSUES = (20, 25, 26, 27, 28, 29, 33, 35, 36, 37, 38, 39, 40, 44, 45, 46, 47)
AC_TOTAL_FLOOR = 5  # every ticket in #11-#48 carries these five acceptance criteria

# ---------------------------------------------------------------------------
# Representation A: hand-written literal registry.
#   n -> (state, raw_checkbox_total, raw_checkbox_checked)
# The acceptance-criteria projection is 5 rows per ticket (AC_TOTAL_FLOOR); the
# extra raw checkboxes are the child-ticket container blocks outside the
# "## Acceptance criteria" section, which are counted and named separately.
# ---------------------------------------------------------------------------
ISSUE_REGISTRY = {
    11: ("CLOSED", 5, 5),
    12: ("CLOSED", 5, 5),
    13: ("CLOSED", 5, 0),
    14: ("CLOSED", 5, 0),
    15: ("CLOSED", 5, 5),
    16: ("CLOSED", 5, 5),
    17: ("CLOSED", 5, 5),
    18: ("CLOSED", 5, 0),
    19: ("CLOSED", 5, 0),
    20: ("OPEN", 9, 0),
    21: ("CLOSED", 5, 0),
    22: ("CLOSED", 5, 0),
    23: ("CLOSED", 5, 5),
    24: ("CLOSED", 5, 5),
    25: ("CLOSED", 11, 0),
    26: ("OPEN", 8, 0),
    27: ("OPEN", 8, 0),
    28: ("OPEN", 8, 0),
    29: ("OPEN", 8, 0),
    30: ("CLOSED", 5, 0),
    31: ("CLOSED", 5, 0),
    32: ("CLOSED", 5, 0),
    33: ("OPEN", 8, 0),
    34: ("CLOSED", 5, 5),
    35: ("CLOSED", 11, 0),
    36: ("CLOSED", 9, 0),
    37: ("CLOSED", 9, 0),
    38: ("CLOSED", 8, 0),
    39: ("OPEN", 8, 0),
    40: ("CLOSED", 8, 0),
    41: ("CLOSED", 5, 0),
    42: ("CLOSED", 5, 0),
    43: ("CLOSED", 5, 0),
    44: ("CLOSED", 9, 0),
    45: ("CLOSED", 10, 0),
    46: ("OPEN", 8, 0),
    47: ("CLOSED", 10, 0),
    48: ("CLOSED", 5, 0),
}


def registry_ac_total(n: int) -> int:
    return AC_TOTAL_FLOOR


def registry_ac_checked(n: int) -> int:
    return ISSUE_REGISTRY[n][2]


def registry_ac_ids(n: int) -> list[str]:
    """Canonical AC ids of one issue: {n}:{k}, k is the 1-based position inside
    the acceptance section (the container block is excluded)."""
    return [f"{n}:{k}" for k in range(1, registry_ac_total(n) + 1)]

# Representation A, second half: raw issue-body digest and UTF-8 byte length,
# hand-transcribed from the capture. A body edit on GitHub must fail here.
BODY_PINS = {
    11: ("ad5b8adb9fe205beb5c71288b45c87c9279a49b3f34d5c91018362f7a37e699d", 1633),
    12: ("bfdde393b9133c1307fc1034a8d4c62f716bef1675e7186208871cd9faf1cc10", 1649),
    13: ("bccb841f7eb8280123b5f90faf61da7636745538afb202600eecfe42a452f792", 1624),
    14: ("83ed0e6f3fb159774da5704f5391b494d7f7aae910abea88246916372d87da80", 1612),
    15: ("f707d4356ae91d79e8fe279515df2cf33319f65bdc4fd2063c6f75be4070207a", 1812),
    16: ("b93c867b201e5a122442acf49417aaf19107a1d7190fb88a95fc8c3e585caaa3", 1549),
    17: ("c715ccc3ae63fc55dfb0ea40e05ee26cee9cef7c50b82af604456cd3870bfd04", 1597),
    18: ("b25146c14f1ec8892c6e8d62cb106cac72bd0809086a8bf52e9cd766f32e50cc", 1875),
    19: ("9390b569e787e6527ecdbc20f91dfbf40b079529039990ed9f5192c6e79580f0", 1804),
    20: ("2e9cdc82b77391900b05a06636bfd8437cf9e301f4ceb1dafb6c08dd01693230", 2485),
    21: ("bce59920dbdb9a437e75f6d4992a3196021eb06048c52a32ff081b26b7b775ce", 1712),
    22: ("6ffdff99595548c0e52fd619c5351ee6783ef11f1f851a9a9606700eb3a8de2d", 1823),
    23: ("fa74395c31dc27a8635ba8cf5b4ce41a1b1844eda08242b56c717d5af7fc9973", 1623),
    24: ("f3bfcaebc7d6e51a8844dc6f8be7b9d0b1365714e886e2f48d4ad8be834673b4", 1724),
    25: ("7ccd8cd7249a07d4ed87c22b4707799e64b081ef47c6d5bd41c64f5f9967640f", 2559),
    26: ("dbee4a3d6980bd89885f6e71ea63ed3ff6469a9e3b2443b8346ef52c8ebc7f2e", 2384),
    27: ("63e63cd89c3dbd6d02d3727d66debd14730d43d9c01665f9b6177cc579d1d362", 2401),
    28: ("ca4e4af79f4fdd62018a906444b919721771ac03079151221dcb1d87086f73ef", 2280),
    29: ("3bc4f09278255cfa895429f740f47b80a5734f60b7aa5bb215dad09af38ec094", 2414),
    30: ("653fe4164791d9f5bd30ed78fccb13989dafb692a49c826a90e154e9fc82d363", 1623),
    31: ("17c58fc8a284b61076f31e4c954093061ff561fe2f5e1f4137be499842b99c8d", 1627),
    32: ("262d58b500203e09e70e21077f4e8cb96203b5a8498271b43df9de80bdd8e723", 1763),
    33: ("b0e09a9a9b7ff39b610934a3b3c3d68a3c02c77103f833013947b5bae46197d7", 2300),
    34: ("525405d2c6dc0db07a652e888d00449e83bdee9a669b4ac71b533a8907a90d4b", 1748),
    35: ("65f60d98c7936e09b98c06a00baa819c7cbbe0a7a4955b2945db7215606917c2", 2394),
    36: ("49e25b88153f63ae5ff9bb54b149fc917ff6544fad9a883ec239d42e0fa6ad7b", 2196),
    37: ("183cc29f239ca8f881a658f211dd27394b0c56c6b9c5d5a87792d3da9fe3fef4", 2165),
    38: ("63965c8b9437f1ce163515ee4f8271dcdfda39990c5a4336788b9e15008a8a54", 2412),
    39: ("b21b995945965e95538c49ed6987557c67c6bc079266eb45d490832c1c7f6995", 2546),
    40: ("0a4b085981527317d92e0222e42e675e7b5141e4a197a2af5251a3d607a071cf", 2413),
    41: ("15c8e28a1db6028042f3dcf002248fa1f4e7a9ffe7a4487391bb8aeec761db62", 1951),
    42: ("57fc693256c7780c0ad151c870753529c3f938b5ac27404ddd2a3ad2bba3e3b3", 1651),
    43: ("2256d8333c5c3e5e38d7d34f46cc7a75292cb3964e260d5c76b1c3fe79869236", 1815),
    44: ("2267fd3848cb3fef701d853562a8b77c1e440a17b9d46b0d09e23eeb3c86b18e", 2334),
    45: ("fbe88a115ffcd70e8a38ddfe5fbaaf862a956a1bd771f8e770616a4cef3e63db", 2452),
    46: ("3bbcb0541b0eaff6d422e5abe0ac5e14f6b3ebf9f27ede11455de9091c3e2629", 2439),
    47: ("0247dddd3d9073e73430615fc22f010fd9eb31bbf2b05b00b285983333512a74", 2505),
    48: ("7b6c46932ffd432c20030b20f7b20e1d715f83ec91cdc8b588ba50dad224936e", 2391),
}

# Literal sets derived by hand from ISSUE_REGISTRY.
EXPECTED_CLOSED_UNCHECKED = (
    13, 14, 18, 19, 21, 22, 25, 30, 31, 32, 35, 36, 37, 38, 40, 41, 42, 43, 44, 45, 47, 48,
)
EXPECTED_OPEN_UNCHECKED = (20, 26, 27, 28, 29, 33, 39, 46)
EXPECTED_CLOSED_ALL_CHECKED = (11, 12, 15, 16, 17, 23, 24, 34)
EXPECTED_DRIFTED_TICKED = (("17", 1), ("17", 2))

ALLOWED_PRIORITY_CLASSES = {
    "zero-native-implementation",
    "zero-native-verification",
    "blocked-native",
    "blocked-matlab",
    "blocked-owner-decision",
    "blocked-abi-vendor",
}
EXPECTED_QUEUE_CLASS = {
    "Q01": "blocked-owner-decision",
    "Q02": "zero-native-implementation",
    "Q03": "zero-native-implementation",
    "Q04": "blocked-native",
    "Q05": "zero-native-verification",
    "Q06": "blocked-owner-decision",
    "Q07": "blocked-native",
    "Q08": "zero-native-verification",
    "Q09": "zero-native-implementation",
    "Q10": "blocked-native",
    "Q11": "blocked-native",
    "Q12": "blocked-abi-vendor",
    "Q13": "blocked-native",
    "Q14": "zero-native-verification",
    "Q15": "zero-native-implementation",
    "Q16": "zero-native-implementation",
    "Q17": "zero-native-implementation",
    "Q18": "blocked-native",
    "Q19": "zero-native-verification",
    "Q20": "zero-native-verification",
    "Q21": "zero-native-verification",
    "Q22": "zero-native-implementation",
    "Q23": "blocked-native",
    "Q24": "zero-native-verification",
    "Q25": "blocked-matlab",
    "Q26": "zero-native-implementation",
    "Q27": "zero-native-implementation",
    "Q28": "blocked-native",
    "Q29": "blocked-native",
    "Q30": "blocked-native",
    "Q31": "blocked-native",
    "Q32": "zero-native-verification",
}

SNAPSHOT_TOP_KEYS = {"schema", "slice_id", "repository", "captured_at", "head",
                     "source_commands", "body_encoding", "issue_range", "issues"}
SNAPSHOT_ISSUE_KEYS = {"number", "state", "title", "url", "updated_at",
                       "body_sha256", "body_bytes", "body"}
LEDGER_TOP_KEYS = {"schema", "slice_id", "generated_at", "repository", "head", "scope",
                   "inputs", "counts", "issue_universe", "ac_universe", "issues",
                   "exact_sets", "ambiguity", "next_work_queue", "verdict", "limitations"}
LEDGER_ISSUE_KEYS = {"number", "state", "title", "url", "updated_at", "body_sha256",
                     "raw_checkbox_total", "raw_checked", "raw_unchecked",
                     "ac_total", "checked", "unchecked",
                     "checked_ordinals", "unchecked_ordinals", "row_digests",
                     "acceptance_heading_count", "ac_items_outside_acceptance_section",
                     "zero_checkbox_issue", "rows"}
LEDGER_AC_ROW_KEYS = {"issue", "ordinal", "id", "checked", "text", "text_sha256",
                      "line", "indent", "in_acceptance_section"}
QUEUE_KEYS = {"rank", "slice_id", "title", "priority_class", "blocks_claim", "gate",
              "ac_refs", "omitted_acs", "evidence", "why", "closure_rule"}
AMBIGUITY_KEYS = {"malformed_checkbox_lines", "non_acceptance_checkboxes",
                  "non_checkbox_list_bracket_lines", "duplicate_text_within_issue",
                  "empty_text_rows", "issues_with_zero_checkboxes",
                  "issues_without_acceptance_heading", "notes"}
COUNTS_KEYS = {
    "ac_checked", "ac_total", "ac_unchecked", "ambiguity_findings", "closed",
    "closed_with_unchecked", "issue_sum", "issues", "issues_with_all_checked",
    "issues_with_zero_checkboxes", "non_acceptance_checkboxes", "open",
    "open_with_unchecked", "raw_checkboxes", "raw_checked",
}
INPUTS_KEYS = {
    "advisory_inputs_never_counted_as_committed", "body_encoding", "build_tool",
    "capture_method", "cited_sources", "local_evidence_pins", "mandated_reads",
    "raw_capture_sha256", "raw_captures", "raw_captures_are_unfiltered_supersets",
    "snapshot_file", "snapshot_sha256", "source_commands",
    "source_snapshot_identity", "test_runtime_dependencies", "text_normalization",
}
SOURCE_SNAPSHOT_IDENTITY_KEYS = {
    "advisory_capture_is_not_a_test_runtime_dependency",
    "copied_from_advisory_capture", "head", "path", "sha256",
}
VERDICT_KEYS = {
    "claims_acceptance", "closed_state_equals_fulfilled", "fail_closed",
    "full_program", "gate_claims", "network_used_during_tests", "snapshot_only",
}
SCOPE_KEYS = {"in_scope", "non_claims", "objective", "out_of_scope"}
EXACT_SETS_KEYS = {
    "all_checked_issues", "checked", "closed_with_all_checked_issues",
    "closed_with_unchecked_issues", "open_with_all_checked_issues",
    "open_with_unchecked_issues", "ticked_but_drifted", "unchecked",
}
AC_UNIVERSE_KEYS = {
    "checked", "definition", "id_format", "non_acceptance_checkboxes",
    "raw_checkboxes_parsed", "row_key_fields", "section_exclusions",
    "total", "unchecked",
}

AC_HEADING_RE = re.compile(r"^#{1,6}\s*Acceptance criteria\s*$", re.IGNORECASE)
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
BULLET_MARKS = "-*+"
LINK_RE = re.compile(r"\]\([^)]*\)")

_snapshot_cache: dict | None = None
_ledger_cache: dict | None = None


def _read_json(path: Path) -> dict:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


def snapshot() -> dict:
    global _snapshot_cache
    if _snapshot_cache is None:
        _snapshot_cache = _read_json(SNAPSHOT)
    return _snapshot_cache


def ledger() -> dict:
    global _ledger_cache
    if _ledger_cache is None:
        _ledger_cache = _read_json(LEDGER)
    return _ledger_cache


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def parse_checkbox_line(line: str, lineno: int) -> dict | None:
    """Parse one Markdown task-list item; None for anything else."""
    stripped = line.lstrip(" \t")
    indent = len(line) - len(stripped)
    if not stripped or stripped[0] not in BULLET_MARKS:
        return None
    rest = stripped[1:]
    if not rest or rest[0] not in " \t":
        return None
    rest = rest.lstrip(" \t")
    if len(rest) < 3 or rest[0] != "[" or rest[2] != "]":
        return None
    mark = rest[1]
    if mark not in (" ", "x", "X"):
        return None
    text = rest[3:]
    if text and text[0] not in " \t":
        return None
    return {
        "checked": mark in ("x", "X"),
        "text": normalize_text(text),
        "line": lineno,
        "indent": indent,
    }


def malformed_reason(line: str, lineno: int) -> str | None:
    """Why ``line`` is a broken checkbox *attempt*, or None if it is not one.

    Ordinary Markdown links are not attempts and are never reported here.
    """
    if parse_checkbox_line(line, lineno) is not None:
        return None
    if LINK_RE.search(line):
        return None
    head = re.match(r"^\s*[-*+]\s+", line.rstrip())
    if head is None:
        return None
    tail = line[head.end():]
    if not tail.startswith("["):
        return None
    token = re.match(r"\[([^\]]*)\]", tail)
    if token is None:
        return "unclosed bracket"
    inner = token.group(1)
    after = line[head.end() + token.end():]
    if inner == "":
        return "empty bracket marker"
    if inner in ("x", "X") and not after.startswith((" ", "\t")):
        return "separator whitespace missing after the marker"
    if len(inner) == 1:
        return "unknown marker character"
    if len(inner) > 1 and inner[0] in (" ", "x", "X"):
        return "second bracket token after the marker"
    return "malformed bracket token"


def find_malformed_checkboxes(body: str) -> list[dict]:
    out = []
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines):
        reason = malformed_reason(line, idx + 1)
        if reason is not None:
            out.append({"line": idx + 1, "raw": line, "reason": reason})
    return out


def find_non_checkbox_bracket_lines(body: str) -> list[int]:
    """List-item bracket lines that are links, not task items."""
    out = []
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines):
        if parse_checkbox_line(line, idx + 1) is not None:
            continue
        if re.match(r"^\s*[-*+]\s*\[", line):
            out.append(idx + 1)
    return out


def acceptance_line_ranges(body: str) -> list[tuple[int, int]]:
    """0-based [start, end) line ranges of every ``## Acceptance criteria`` section."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ranges: list[tuple[int, int]] = []
    start = None
    for idx, line in enumerate(lines):
        if AC_HEADING_RE.match(line):
            if start is not None:
                ranges.append((start, idx))
            start = idx + 1
        elif ANY_HEADING_RE.match(line) and start is not None:
            ranges.append((start, idx))
            start = None
    if start is not None:
        ranges.append((start, len(lines)))
    return ranges


def extract_section_scoped(body: str) -> dict:
    """Representation B extractor: Markdown-structure walk.

    ``in_section``/``outside_section`` are the two projections; ``all_rows`` is the
    same single walk emitted in body order (a different code path from the flat
    token scan in :func:`extract_flat`).
    """
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ranges = acceptance_line_ranges(body)
    covered = {i for lo, hi in ranges for i in range(lo, hi)}
    all_rows: list[dict] = []
    for idx, line in enumerate(lines):
        hit = parse_checkbox_line(line, idx + 1)
        if hit is not None:
            all_rows.append({**hit, "in_section": idx in covered})
    inside = [r for r in all_rows if r["in_section"]]
    outside = [r for r in all_rows if not r["in_section"]]
    return {
        "heading_count": len(ranges),
        "all_rows": all_rows,
        "in_section": inside,
        "outside_section": outside,
    }


def extract_flat(body: str) -> list[dict]:
    """Raw checkbox scan in body order, independent of headings."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [h for idx, line in enumerate(lines)
            if (h := parse_checkbox_line(line, idx + 1)) is not None]


def issue_index(snap: dict) -> dict:
    return {i["number"]: i for i in snap["issues"]}


def ledger_index(led: dict) -> dict:
    return {i["number"]: i for i in led["issues"]}


def ledger_ac_rows(led: dict) -> list[dict]:
    return [r for i in led["issues"] for r in i["rows"] if r["in_acceptance_section"]]


def checked_ids(led: dict) -> set[str]:
    return {r["id"] for r in ledger_ac_rows(led) if r["checked"]}


def unchecked_ids(led: dict) -> set[str]:
    return {r["id"] for r in ledger_ac_rows(led) if not r["checked"]}


def independent_gap_issue_sets(snap: dict) -> tuple[list[int], list[int], list[int]]:
    """Rederive CLOSED-with-gaps / OPEN-with-gaps / CLOSED-all-ticked from bodies."""
    closed_u, open_u, closed_all = [], [], []
    for issue in snap["issues"]:
        unchecked = sum(
            1 for r in extract_section_scoped(issue["body"])["in_section"]
            if not r["checked"]
        )
        if issue["state"] == "CLOSED" and unchecked > 0:
            closed_u.append(issue["number"])
        elif issue["state"] == "OPEN" and unchecked > 0:
            open_u.append(issue["number"])
        elif issue["state"] == "CLOSED" and unchecked == 0:
            closed_all.append(issue["number"])
    return closed_u, open_u, closed_all


def expected_omitted_acs(q: dict, unchecked: set[str]) -> list[str]:
    cited_issues = {int(ref.split(":")[0]) for ref in q["ac_refs"]}
    want = {rid for rid in unchecked if int(rid.split(":")[0]) in cited_issues}
    want -= set(q["ac_refs"])
    return sorted(want, key=lambda rid: (int(rid.split(":")[0]), int(rid.split(":")[1])))


def accept_plan_doc(text: str) -> bool:
    if "not-closed" not in text or "Full = closed" in text:
        return False
    if EXPECTED_SNAPSHOT_REL not in text or EXPECTED_HEAD not in text:
        return False
    if "| 未勾选 AC | **150** |" not in text:
        return False
    if "| CLOSED 且仍有未勾选 AC | 22 |" not in text:
        return False
    if "| OPEN 且仍有未勾选 AC | 8 |" not in text:
        return False
    if "#47、#48" not in text:
        return False
    total = re.search(
        r"^\|\s*\*\*合计\*\*\s*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|",
        text, re.M,
    )
    if total is None:
        return False
    got = [int(re.sub(r"[^0-9]", "", g)) for g in total.groups()]
    return got == [255, 40, 190, 40, 150, 65]


def path_is_ignored_untracked(rel: str) -> bool:
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", rel], cwd=REPO
    ).returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=REPO,
        capture_output=True, text=True,
    ).returncode == 0
    return ignored and not tracked


# ---------------------------------------------------------------------------
class SnapshotIntegrityTests(unittest.TestCase):
    def test_snapshot_schema_keys(self):
        snap = snapshot()
        self.assertEqual(set(snap.keys()), SNAPSHOT_TOP_KEYS)
        for issue in snap["issues"]:
            self.assertEqual(set(issue.keys()), SNAPSHOT_ISSUE_KEYS, issue["number"])

    def test_issue_universe_matches_literal_registry(self):
        numbers = [i["number"] for i in snapshot()["issues"]]
        self.assertEqual(len(numbers), EXPECTED_ISSUE_COUNT)
        self.assertEqual(numbers, sorted(numbers), "issues must be ascending")
        self.assertEqual(numbers, list(range(ISSUE_FIRST, ISSUE_LAST + 1)),
                         "issue range must be contiguous: no gap, no duplicate")
        self.assertEqual(sum(numbers), EXPECTED_ISSUE_SUM)
        self.assertEqual(set(numbers), set(ISSUE_REGISTRY))

    def test_states_match_literal_registry(self):
        for issue in snapshot()["issues"]:
            self.assertEqual(issue["state"], ISSUE_REGISTRY[issue["number"]][0],
                             f"#{issue['number']} state")

    def test_body_digests_and_lengths_match_literal_pins(self):
        for issue in snapshot()["issues"]:
            n = issue["number"]
            digest = sha256_text(issue["body"])
            self.assertEqual(digest, issue["body_sha256"], f"#{n} self-consistent digest")
            self.assertEqual(len(issue["body"].encode("utf-8")), issue["body_bytes"],
                             f"#{n} byte length")
            self.assertEqual((digest, issue["body_bytes"]), BODY_PINS[n],
                             f"#{n} body changed since the frozen capture")

    def test_urls_are_canonical(self):
        for issue in snapshot()["issues"]:
            self.assertEqual(issue["url"],
                             f"https://github.com/unununnnn/wksim/issues/{issue['number']}")

    def test_body_encoding_declared_utf8_no_bom(self):
        self.assertEqual(snapshot()["body_encoding"], "utf-8-no-bom")
        self.assertFalse(SNAPSHOT.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_no_checkbox_line_is_malformed(self):
        for issue in snapshot()["issues"]:
            self.assertEqual(find_malformed_checkboxes(issue["body"]), [],
                             f"#{issue['number']} malformed checkbox-like lines")

    def test_malformed_detector_self_test(self):
        """Disabled variants must fire; enabled formats and links must not."""
        should_fire = (
            "- [] text",
            "- []text",
            "- []",
            "- [y] text",
            "- [?] text",
            "- [x text",
            "- [x][x] text",
            "- [ x] text",
            "- [x]no space",
            "- [] text\n- [x] yes",
        )
        should_not_fire = (
            "- [ ] text",
            "- [ ]",
            "- [x] text",
            "* [X] text",
            "+ [ ] text",
            "* [ ]",
            "  + [ ]   ",
            "  - [ ] text",
            "- [title](https://example.invalid/1)",
            "- [title](https://example.invalid/1) and more",
            "- [实验能力预检与候选身份核验](https://github.com/unununnnn/wksim/issues/11)",
            "plain text [ ] here",
            "- plain bullet",
            "# heading",
            "<!-- container -->",
        )
        for line in should_fire:
            self.assertTrue(find_malformed_checkboxes(line),
                            f"detector missed malformed form: {line!r}")
        for line in should_not_fire:
            self.assertEqual(find_malformed_checkboxes(line), [],
                             f"detector false positive on: {line!r}")


class ExtractorsAgreeTests(unittest.TestCase):
    def test_flat_and_section_scoped_extraction_agree(self):
        for issue in snapshot()["issues"]:
            flat = extract_flat(issue["body"])
            scoped = extract_section_scoped(issue["body"])["all_rows"]
            n = issue["number"]
            self.assertEqual(len(flat), len(scoped), f"#{n} count")
            self.assertEqual([r["text"] for r in flat], [r["text"] for r in scoped],
                             f"#{n} text order")
            self.assertEqual([r["checked"] for r in flat], [r["checked"] for r in scoped],
                             f"#{n} checked order")
            self.assertEqual([r["line"] for r in flat], [r["line"] for r in scoped],
                             f"#{n} line order")
            self.assertEqual([r["indent"] for r in flat], [r["indent"] for r in scoped],
                             f"#{n} indent order")

    def test_counts_match_literal_registry(self):
        for issue in snapshot()["issues"]:
            n = issue["number"]
            _, want_raw, want_raw_checked = ISSUE_REGISTRY[n]
            want_ac, want_ac_checked = registry_ac_total(n), registry_ac_checked(n)
            flat = extract_flat(issue["body"])
            scoped = extract_section_scoped(issue["body"])
            self.assertEqual(len(flat), want_raw, f"#{n} raw checkbox total")
            self.assertEqual(sum(1 for r in flat if r["checked"]), want_raw_checked,
                             f"#{n} raw checked")
            self.assertEqual(len(scoped["in_section"]), want_ac, f"#{n} acceptance-section rows")
            self.assertEqual(sum(1 for r in scoped["in_section"] if r["checked"]),
                             want_ac_checked, f"#{n} acceptance-section checked")

    def test_totals_match_literal_constants(self):
        flat = [r for i in snapshot()["issues"] for r in extract_flat(i["body"])]
        ac = [r for i in snapshot()["issues"] for r in extract_section_scoped(i["body"])["in_section"]]
        non_ac = [r for i in snapshot()["issues"]
                  for r in extract_section_scoped(i["body"])["outside_section"]]
        self.assertEqual(len(flat), EXPECTED_RAW_CHECKBOXES)
        self.assertEqual(sum(1 for r in flat if r["checked"]), EXPECTED_RAW_CHECKED)
        self.assertEqual(len(ac), EXPECTED_AC_TOTAL)
        self.assertEqual(sum(1 for r in ac if r["checked"]), EXPECTED_AC_CHECKED)
        self.assertEqual(sum(1 for r in ac if not r["checked"]), EXPECTED_AC_UNCHECKED)
        self.assertEqual(len(non_ac), EXPECTED_NON_AC_CHECKBOXES)
        self.assertEqual(len(ac) + len(non_ac), len(flat))


class LedgerIntegrityTests(unittest.TestCase):
    def test_ledger_schema_keys(self):
        led = ledger()
        self.assertEqual(set(led.keys()), LEDGER_TOP_KEYS)
        self.assertEqual(set(led["counts"].keys()), COUNTS_KEYS)
        self.assertEqual(set(led["inputs"].keys()), INPUTS_KEYS)
        self.assertEqual(set(led["verdict"].keys()), VERDICT_KEYS)
        self.assertEqual(set(led["scope"].keys()), SCOPE_KEYS)
        self.assertEqual(set(led["exact_sets"].keys()), EXACT_SETS_KEYS)
        self.assertEqual(set(led["ac_universe"].keys()), AC_UNIVERSE_KEYS)
        self.assertEqual(set(led["inputs"]["source_snapshot_identity"].keys()),
                         SOURCE_SNAPSHOT_IDENTITY_KEYS)
        for issue in led["issues"]:
            self.assertEqual(set(issue.keys()), LEDGER_ISSUE_KEYS, issue["number"])
            for row in issue["rows"]:
                self.assertEqual(set(row.keys()), LEDGER_AC_ROW_KEYS, row["id"])

    def test_head_and_snapshot_identity_are_pinned(self):
        led = ledger()
        snap = snapshot()
        self.assertEqual(led["head"], EXPECTED_HEAD)
        self.assertEqual(snap["head"], EXPECTED_HEAD)
        self.assertEqual(led["repository"], "unununnnn/wksim")
        self.assertEqual(snap["repository"], "unununnnn/wksim")
        self.assertEqual(led["inputs"]["snapshot_file"], EXPECTED_SNAPSHOT_REL)
        self.assertEqual(led["inputs"]["snapshot_sha256"], EXPECTED_SNAPSHOT_SHA256)
        self.assertEqual(sha256_bytes(SNAPSHOT.read_bytes()), EXPECTED_SNAPSHOT_SHA256)
        ident = led["inputs"]["source_snapshot_identity"]
        self.assertEqual(ident["path"], EXPECTED_SNAPSHOT_REL)
        self.assertEqual(ident["sha256"], EXPECTED_SNAPSHOT_SHA256)
        self.assertEqual(ident["head"], EXPECTED_HEAD)
        self.assertTrue(ident["advisory_capture_is_not_a_test_runtime_dependency"])
        self.assertEqual(led["ac_universe"]["id_format"], EXPECTED_ID_FORMAT)
        self.assertEqual(SNAPSHOT, REPO / EXPECTED_SNAPSHOT_REL)
        self.assertFalse(path_is_ignored_untracked(EXPECTED_SNAPSHOT_REL))
        self.assertNotIn("coordination", EXPECTED_SNAPSHOT_REL)

    def test_id_format_matches_acceptance_section_ordinals(self):
        led = ledger()
        self.assertEqual(led["ac_universe"]["id_format"], EXPECTED_ID_FORMAT)
        issue20 = next(i for i in led["issues"] if i["number"] == 20)
        first_ac = next(r for r in issue20["rows"] if r["in_acceptance_section"])
        self.assertEqual(first_ac["id"], "20:1")
        self.assertEqual(first_ac["ordinal"], 5)
        ord5 = next(r for r in issue20["rows"] if r["ordinal"] == 5)
        self.assertEqual(ord5["id"], "20:1")
        self.assertNotIn("all parsed checkboxes of the issue in body order",
                         led["ac_universe"]["id_format"])

    def test_ledger_declares_fail_closed_policy(self):
        v = ledger()["verdict"]
        self.assertTrue(v["fail_closed"])
        self.assertFalse(v["claims_acceptance"])
        self.assertFalse(v["closed_state_equals_fulfilled"])
        self.assertEqual(v["full_program"], "not-closed")
        self.assertTrue(v["snapshot_only"])
        self.assertFalse(v["network_used_during_tests"])
        self.assertEqual(set(v["gate_claims"].values()), {"not-closed"})

    def test_ledger_issue_universe_matches_snapshot_and_literals(self):
        led = ledger()
        numbers = [i["number"] for i in led["issues"]]
        self.assertEqual(numbers, list(range(ISSUE_FIRST, ISSUE_LAST + 1)))
        self.assertEqual(set(numbers), set(ISSUE_REGISTRY))
        for issue in led["issues"]:
            src = issue_index(snapshot())[issue["number"]]
            for key in ("state", "title", "url", "body_sha256"):
                self.assertEqual(issue[key], src[key], f"#{issue['number']} {key}")
            self.assertEqual(issue["updated_at"], src["updated_at"])

    def test_ledger_rows_reproduce_snapshot_extraction_exactly(self):
        led = ledger()
        for issue in led["issues"]:
            n = issue["number"]
            source = extract_flat(issue_index(snapshot())[n]["body"])
            scoped = extract_section_scoped(issue_index(snapshot())[n]["body"])
            rows = issue["rows"]
            self.assertEqual(len(rows), len(source), f"#{n} row count")
            self.assertEqual([r["ordinal"] for r in rows], list(range(1, len(source) + 1)),
                             f"#{n} ordinals")
            expected_ids = []
            in_section_seen = 0
            for row in rows:
                if row["in_acceptance_section"]:
                    in_section_seen += 1
                    expected_ids.append(f"{n}:{in_section_seen}")
                else:
                    expected_ids.append(f"{n}:x{row['ordinal']}")
            self.assertEqual([r["id"] for r in rows], expected_ids, f"#{n} id shape")
            for row, src in zip(rows, source):
                self.assertEqual(row["checked"], src["checked"], f"#{n}:{row['ordinal']} state")
                self.assertEqual(row["text"], src["text"], f"#{n}:{row['ordinal']} text")
                self.assertEqual(row["line"], src["line"], f"#{n}:{row['ordinal']} line")
                self.assertEqual(row["indent"], src["indent"], f"#{n}:{row['ordinal']} indent")
                self.assertEqual(row["text_sha256"], sha256_text(src["text"]))
            # the in-section projection must equal the section-scoped extractor
            in_section = [r for r in rows if r["in_acceptance_section"]]
            self.assertEqual([r["line"] for r in in_section],
                             [r["line"] for r in scoped["in_section"]], f"#{n} in-section set")
            self.assertEqual([r["line"] for r in rows if not r["in_acceptance_section"]],
                             [r["line"] for r in scoped["outside_section"]],
                             f"#{n} outside-section set")
            self.assertEqual(issue["row_digests"], [r["text_sha256"] for r in rows])
            self.assertEqual(issue["acceptance_heading_count"], scoped["heading_count"])
            self.assertEqual(issue["ac_items_outside_acceptance_section"],
                             len(scoped["outside_section"]))

    def test_ledger_per_issue_counts_match_literals(self):
        for issue in ledger()["issues"]:
            n = issue["number"]
            _, want_raw, want_raw_checked = ISSUE_REGISTRY[n]
            want_ac, want_ac_checked = registry_ac_total(n), registry_ac_checked(n)
            self.assertEqual(issue["raw_checkbox_total"], want_raw, f"#{n} raw total")
            self.assertEqual(issue["raw_checked"], want_raw_checked, f"#{n} raw checked")
            self.assertEqual(issue["raw_unchecked"], want_raw - want_raw_checked, f"#{n} raw unchecked")
            self.assertEqual(issue["ac_total"], want_ac, f"#{n} ac total")
            self.assertEqual(issue["checked"], want_ac_checked, f"#{n} ac checked")
            self.assertEqual(issue["unchecked"], want_ac - want_ac_checked, f"#{n} ac unchecked")
            self.assertEqual(len(issue["rows"]), want_raw, f"#{n} parsed rows")
            self.assertEqual(len(issue["checked_ordinals"]), want_ac_checked, f"#{n} checked ordinals")
            self.assertEqual(len(issue["unchecked_ordinals"]), want_ac - want_ac_checked,
                             f"#{n} unchecked ordinals")
            in_section = [r for r in issue["rows"] if r["in_acceptance_section"]]
            self.assertEqual(len(in_section), want_ac, f"#{n} in-section rows")
            self.assertEqual(sorted(issue["checked_ordinals"]),
                             [r["ordinal"] for r in in_section if r["checked"]], f"#{n} ordinals")
            self.assertEqual(sorted(issue["unchecked_ordinals"]),
                             [r["ordinal"] for r in in_section if not r["checked"]], f"#{n} gaps")
            self.assertEqual(issue["zero_checkbox_issue"], want_raw == 0, f"#{n} zero flag")

    def test_ledger_counts_match_literals_and_snapshot(self):
        led = ledger()
        counts = led["counts"]
        ac = [r for i in snapshot()["issues"]
              for r in extract_section_scoped(i["body"])["in_section"]]
        self.assertEqual(counts["issues"], EXPECTED_ISSUE_COUNT)
        self.assertEqual(counts["issue_sum"], EXPECTED_ISSUE_SUM)
        self.assertEqual(counts["raw_checkboxes"], EXPECTED_RAW_CHECKBOXES)
        self.assertEqual(counts["raw_checkboxes"], sum(len(extract_flat(i["body"]))
                                                       for i in snapshot()["issues"]))
        self.assertEqual(counts["raw_checked"], EXPECTED_RAW_CHECKED)
        self.assertEqual(counts["ac_total"], EXPECTED_AC_TOTAL)
        self.assertEqual(counts["ac_total"], len(ac))
        self.assertEqual(counts["ac_checked"], EXPECTED_AC_CHECKED)
        self.assertEqual(counts["ac_checked"], sum(1 for r in ac if r["checked"]))
        self.assertEqual(counts["ac_unchecked"], EXPECTED_AC_UNCHECKED)
        self.assertEqual(counts["ac_checked"] + counts["ac_unchecked"], counts["ac_total"])
        self.assertEqual(counts["non_acceptance_checkboxes"], EXPECTED_NON_AC_CHECKBOXES)
        self.assertEqual(counts["non_acceptance_checkboxes"],
                         sum(i["ac_items_outside_acceptance_section"] for i in led["issues"]))
        self.assertEqual(counts["ac_total"] + counts["non_acceptance_checkboxes"],
                         counts["raw_checkboxes"])
        self.assertEqual(len(ledger_ac_rows(led)), EXPECTED_AC_TOTAL)
        closed_u, open_u, closed_all = independent_gap_issue_sets(snapshot())
        self.assertEqual(counts["closed_with_unchecked"], 22)
        self.assertEqual(counts["closed_with_unchecked"], len(EXPECTED_CLOSED_UNCHECKED))
        self.assertEqual(counts["closed_with_unchecked"], len(closed_u))
        self.assertEqual(closed_u, list(EXPECTED_CLOSED_UNCHECKED))
        self.assertEqual(counts["open_with_unchecked"], 8)
        self.assertEqual(counts["open_with_unchecked"], len(EXPECTED_OPEN_UNCHECKED))
        self.assertEqual(counts["open_with_unchecked"], len(open_u))
        self.assertEqual(open_u, list(EXPECTED_OPEN_UNCHECKED))
        self.assertEqual(counts["issues_with_all_checked"], 8)
        self.assertEqual(counts["issues_with_all_checked"], len(EXPECTED_CLOSED_ALL_CHECKED))
        self.assertEqual(closed_all, list(EXPECTED_CLOSED_ALL_CHECKED))
        self.assertEqual(set(led["exact_sets"]["closed_with_unchecked_issues"]),
                         set(EXPECTED_CLOSED_UNCHECKED))
        self.assertEqual(set(led["exact_sets"]["open_with_unchecked_issues"]),
                         set(EXPECTED_OPEN_UNCHECKED))

    def test_no_duplicate_or_missing_ac_ids(self):
        rows = ledger_ac_rows(ledger())
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "duplicate AC ids")
        expected = {rid for n in ISSUE_REGISTRY for rid in registry_ac_ids(n)}
        self.assertEqual(set(ids), expected, "AC id universe mismatch")
        self.assertEqual(len(expected), EXPECTED_AC_TOTAL)

    def test_issues_with_zero_checkboxes_recorded_explicitly(self):
        led = ledger()
        self.assertEqual(led["counts"]["issues_with_zero_checkboxes"], 0)
        for issue in led["issues"]:
            self.assertGreater(issue["raw_checkbox_total"], 0)
            self.assertFalse(issue["zero_checkbox_issue"])
        self.assertEqual([i["number"] for i in led["issues"] if i["zero_checkbox_issue"]], [])
        self.assertEqual(led["ambiguity"]["issues_without_acceptance_heading"], [])

    def test_acceptance_section_present_and_accounted(self):
        for issue in ledger()["issues"]:
            n = issue["number"]
            self.assertEqual(issue["acceptance_heading_count"], 1, f"#{n} acceptance heading count")
            self.assertEqual(issue["ac_total"] + issue["ac_items_outside_acceptance_section"],
                             issue["raw_checkbox_total"], f"#{n} section accounting")


class FailClosedMutationTests(unittest.TestCase):
    """Every falsification below must be rejected."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="acgap-mutation-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _mutated_snapshot(self, mutate) -> dict:
        snap = json.loads(json.dumps(snapshot()))
        mutate(snap)
        path = self.tmp / "mutated_snapshot.json"
        path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        return _read_json(path)

    def _mutated_ledger(self, mutate) -> dict:
        led = json.loads(json.dumps(ledger()))
        mutate(led)
        path = self.tmp / "mutated_ledger.json"
        path.write_text(json.dumps(led, ensure_ascii=False), encoding="utf-8")
        return _read_json(path)

    # -- independent acceptance predicates (mirror the real checks) --------
    def _accept_snapshot(self, snap: dict) -> bool:
        try:
            numbers = [i["number"] for i in snap["issues"]]
            if numbers != list(range(ISSUE_FIRST, ISSUE_LAST + 1)):
                return False
            for issue in snap["issues"]:
                state, want_raw, want_raw_checked = ISSUE_REGISTRY[issue["number"]]
                want_ac = registry_ac_total(issue["number"])
                want_ac_checked = registry_ac_checked(issue["number"])
                if issue["state"] != state:
                    return False
                if sha256_text(issue["body"]) != issue["body_sha256"]:
                    return False
                if (sha256_text(issue["body"]), issue["body_bytes"]) != BODY_PINS[issue["number"]]:
                    return False
                flat = extract_flat(issue["body"])
                scoped = extract_section_scoped(issue["body"])
                if len(flat) != want_raw:
                    return False
                if sum(1 for r in flat if r["checked"]) != want_raw_checked:
                    return False
                if len(scoped["in_section"]) != want_ac:
                    return False
                if sum(1 for r in scoped["in_section"] if r["checked"]) != want_ac_checked:
                    return False
                if find_malformed_checkboxes(issue["body"]):
                    return False
        except (KeyError, TypeError, AttributeError):
            return False
        return True

    def _accept_ledger(self, led: dict, snap: dict) -> bool:
        try:
            if set(led.keys()) != LEDGER_TOP_KEYS:
                return False
            index = issue_index(snap)
            if [i["number"] for i in led["issues"]] != list(range(ISSUE_FIRST, ISSUE_LAST + 1)):
                return False
            seen: set[str] = set()
            ac_checked = 0
            ac_total = 0
            for issue in led["issues"]:
                if set(issue.keys()) != LEDGER_ISSUE_KEYS:
                    return False
                src = index[issue["number"]]
                if issue["body_sha256"] != src["body_sha256"]:
                    return False
                if issue["state"] != src["state"]:
                    return False
                state, want_raw, want_raw_checked = ISSUE_REGISTRY[issue["number"]]
                want_ac = registry_ac_total(issue["number"])
                want_ac_checked = registry_ac_checked(issue["number"])
                if issue["raw_checkbox_total"] != want_raw or issue["raw_checked"] != want_raw_checked:
                    return False
                if issue["ac_total"] != want_ac or issue["checked"] != want_ac_checked:
                    return False
                source_rows = extract_flat(src["body"])
                scoped = extract_section_scoped(src["body"])
                if len(issue["rows"]) != len(source_rows):
                    return False
                for row, src_row in zip(issue["rows"], source_rows):
                    if set(row.keys()) != LEDGER_AC_ROW_KEYS:
                        return False
                    if row["checked"] != src_row["checked"] or row["text"] != src_row["text"]:
                        return False
                    if row["line"] != src_row["line"]:
                        return False
                    if row["id"] in seen:
                        return False
                    seen.add(row["id"])
                in_section = [r for r in issue["rows"] if r["in_acceptance_section"]]
                if [r["line"] for r in in_section] != [r["line"] for r in scoped["in_section"]]:
                    return False
                ac_total += len(in_section)
                ac_checked += sum(1 for r in in_section if r["checked"])
            expected = {rid for n in ISSUE_REGISTRY for rid in registry_ac_ids(n)}
            if {r["id"] for r in ledger_ac_rows(led)} != expected:
                return False
            if ac_total != EXPECTED_AC_TOTAL or ac_checked != EXPECTED_AC_CHECKED:
                return False
            if led["counts"]["ac_total"] != EXPECTED_AC_TOTAL:
                return False
            if led["counts"]["ac_checked"] != EXPECTED_AC_CHECKED:
                return False
            if led["counts"]["ac_unchecked"] != EXPECTED_AC_UNCHECKED:
                return False
            if led["counts"]["raw_checkboxes"] != EXPECTED_RAW_CHECKBOXES:
                return False
            if len(ledger_ac_rows(led)) != EXPECTED_AC_TOTAL:
                return False
            if set(led["counts"].keys()) != COUNTS_KEYS:
                return False
            if set(led["inputs"].keys()) != INPUTS_KEYS:
                return False
            if set(led["verdict"].keys()) != VERDICT_KEYS:
                return False
            if set(led["scope"].keys()) != SCOPE_KEYS:
                return False
            if led["head"] != EXPECTED_HEAD:
                return False
            if led["ac_universe"]["id_format"] != EXPECTED_ID_FORMAT:
                return False
            if led["inputs"]["snapshot_file"] != EXPECTED_SNAPSHOT_REL:
                return False
            if led["inputs"]["snapshot_sha256"] != EXPECTED_SNAPSHOT_SHA256:
                return False
            closed_u, open_u, closed_all = independent_gap_issue_sets(snap)
            if led["counts"]["closed_with_unchecked"] != 22:
                return False
            if led["counts"]["closed_with_unchecked"] != len(closed_u):
                return False
            if closed_u != list(EXPECTED_CLOSED_UNCHECKED):
                return False
            if led["counts"]["open_with_unchecked"] != 8:
                return False
            if led["counts"]["open_with_unchecked"] != len(open_u):
                return False
            if open_u != list(EXPECTED_OPEN_UNCHECKED):
                return False
            if led["counts"]["issues_with_all_checked"] != len(EXPECTED_CLOSED_ALL_CHECKED):
                return False
            if closed_all != list(EXPECTED_CLOSED_ALL_CHECKED):
                return False
            if not led.get("limitations"):
                return False
            unchecked = unchecked_ids(led)
            if {q["slice_id"] for q in led["next_work_queue"]} != set(EXPECTED_QUEUE_CLASS):
                return False
            for q in led["next_work_queue"]:
                if set(q.keys()) != QUEUE_KEYS:
                    return False
                if q["priority_class"] != EXPECTED_QUEUE_CLASS.get(q["slice_id"]):
                    return False
                if q["omitted_acs"] != expected_omitted_acs(q, unchecked):
                    return False
            cited = set(led["inputs"]["cited_sources"])
            if cited & BANNED_IGNORED_UNTRACKED_EVIDENCE:
                return False
        except (KeyError, TypeError, IndexError, AttributeError):
            return False
        return True

    def assert_rejected_snapshot(self, mutate, why):
        self.assertFalse(self._accept_snapshot(self._mutated_snapshot(mutate)),
                         f"NOT fail-closed: {why}")

    def assert_rejected_ledger(self, mutate, why):
        self.assertFalse(self._accept_ledger(self._mutated_ledger(mutate), snapshot()),
                         f"NOT fail-closed: {why}")

    def test_control_unmutated_artifacts_are_accepted(self):
        """The mutation predicates must accept the frozen artifacts unchanged,
        otherwise every rejection assertion below would be vacuous."""
        self.assertTrue(self._accept_snapshot(snapshot()),
                        "the snapshot predicate rejects the frozen snapshot")
        self.assertTrue(self._accept_ledger(ledger(), snapshot()),
                        "the ledger predicate rejects the frozen ledger")

    # -- mutations ---------------------------------------------------------
    def test_mutation_checkbox_drop(self):
        def mutate(snap):
            issue = next(i for i in snap["issues"] if i["number"] == 15)
            lines = issue["body"].split("\n")
            for idx, line in enumerate(lines):
                if line.startswith("- [x]") and "取消后不再发送后续航点" in line:
                    del lines[idx]
                    break
            issue["body"] = "\n".join(lines)
        self.assert_rejected_snapshot(mutate, "one checkbox line was deleted")

    def test_mutation_checkbox_duplicate(self):
        def mutate(snap):
            issue = next(i for i in snap["issues"] if i["number"] == 15)
            lines = issue["body"].split("\n")
            for idx, line in enumerate(lines):
                if line.startswith("- [x]") and "取消后不再发送后续航点" in line:
                    lines.insert(idx, line)
                    break
            issue["body"] = "\n".join(lines)
        self.assert_rejected_snapshot(mutate, "one checkbox line was duplicated")

    def test_mutation_checked_state_flip_in_snapshot(self):
        def mutate(snap):
            issue = next(i for i in snap["issues"] if i["number"] == 13)
            issue["body"] = issue["body"].replace("- [ ]", "- [x]", 1)
        self.assert_rejected_snapshot(mutate, "an unchecked AC was ticked in the body")

    def test_mutation_checked_state_flip_in_ledger(self):
        def mutate(led):
            issue = next(i for i in led["issues"] if i["number"] == 13)
            issue["rows"][0]["checked"] = True
            issue["checked"] = 1
            issue["unchecked"] = issue["ac_total"] - 1
        self.assert_rejected_ledger(mutate, "the ledger promoted an unchecked AC to checked")

    def test_mutation_body_pin_drift(self):
        def mutate(snap):
            issue = next(i for i in snap["issues"] if i["number"] == 20)
            issue["body"] = issue["body"] + "\n\n- [x] fabricated trailing AC\n"
        self.assert_rejected_snapshot(mutate, "the issue body changed after the capture")

    def test_mutation_body_digest_swap(self):
        def mutate(snap):
            issue = next(i for i in snap["issues"] if i["number"] == 20)
            issue["body"] = issue["body"] + "\n\n- [x] fabricated trailing AC\n"
            issue["body_sha256"] = sha256_text(issue["body"])
        self.assert_rejected_snapshot(mutate, "body + digest were rewritten together")

    def test_mutation_issue_omission(self):
        def mutate(snap):
            snap["issues"] = [i for i in snap["issues"] if i["number"] != 33]
        self.assert_rejected_snapshot(mutate, "issue #33 was dropped from the snapshot")

    def test_mutation_ledger_issue_omission(self):
        def mutate(led):
            led["issues"] = [i for i in led["issues"] if i["number"] != 33]
        self.assert_rejected_ledger(mutate, "issue #33 was dropped from the ledger")

    def test_mutation_issue_range_gap(self):
        def mutate(snap):
            snap["issues"] = [i for i in snap["issues"] if i["number"] not in (30, 31)]
            snap["issues"].append({"number": 49, "state": "OPEN", "title": "x",
                                   "url": "u", "updated_at": "t", "body_sha256": "0" * 64,
                                   "body_bytes": 0, "body": ""})
        self.assert_rejected_snapshot(mutate, "the issue range was made non-contiguous")

    def test_mutation_count_inflation(self):
        def mutate(led):
            led["counts"]["ac_checked"] = led["counts"]["ac_checked"] + 1
        self.assert_rejected_ledger(mutate, "checked count was inflated")

    def test_mutation_count_deflation(self):
        def mutate(led):
            led["counts"]["ac_total"] = led["counts"]["ac_total"] - 1
        self.assert_rejected_ledger(mutate, "total count was deflated")

    def test_mutation_total_inflation_via_extra_row(self):
        def mutate(led):
            issue = next(i for i in led["issues"] if i["number"] == 13)
            clone = json.loads(json.dumps(issue["rows"][0]))
            clone["ordinal"] = len(issue["rows"]) + 1
            clone["id"] = f"13:{clone['ordinal']}"
            issue["rows"].append(clone)
            issue["raw_checkbox_total"] += 1
            issue["raw_unchecked"] += 1
            issue["ac_total"] += 1
            issue["unchecked"] += 1
            led["counts"]["raw_checkboxes"] += 1
            led["counts"]["ac_total"] += 1
            led["counts"]["ac_unchecked"] += 1
        self.assert_rejected_ledger(mutate, "a fabricated AC row was appended")

    def test_mutation_duplicate_ac_id(self):
        def mutate(led):
            issue = next(i for i in led["issues"] if i["number"] == 15)
            issue["rows"][1]["id"] = issue["rows"][0]["id"]
        self.assert_rejected_ledger(mutate, "two rows share one AC id")

    def test_mutation_unknown_schema_key(self):
        def mutate(led):
            led["issues"][0]["extra_key"] = 1
        self.assert_rejected_ledger(mutate, "an unknown issue key was added")

    def test_mutation_unknown_top_level_key(self):
        def mutate(led):
            led["surprise"] = True
        self.assert_rejected_ledger(mutate, "an unknown top-level key was added")

    def test_mutation_section_flag_flip(self):
        def mutate(led):
            issue = next(i for i in led["issues"] if i["number"] == 20)
            for row in issue["rows"]:
                row["in_acceptance_section"] = True
            issue["ac_total"] = issue["raw_checkbox_total"]
            issue["unchecked"] = issue["raw_checkbox_total"]
        self.assert_rejected_ledger(mutate, "container checkboxes were promoted to ACs")

    def test_mutation_checked_promotion_by_removing_row(self):
        def mutate(led):
            issue = next(i for i in led["issues"] if i["number"] == 35)
            issue["rows"] = issue["rows"][:5]
            issue["raw_checkbox_total"] = 5
            issue["ac_total"] = 5
            issue["raw_unchecked"] = 5
            issue["unchecked"] = 5
        self.assert_rejected_ledger(mutate, "unchecked rows were deleted to hide the gap")

    def test_mutation_undercount_closed_with_unchecked_headline(self):
        def mutate(led):
            led["counts"]["closed_with_unchecked"] = 12
        self.assert_rejected_ledger(mutate, "CLOSED-with-gaps headline 22 -> 12")

    def test_mutation_undercount_open_with_unchecked_headline(self):
        def mutate(led):
            led["counts"]["open_with_unchecked"] = 3
        self.assert_rejected_ledger(mutate, "OPEN-with-gaps headline 8 -> 3")

    def test_mutation_undercount_all_checked_headline(self):
        def mutate(led):
            led["counts"]["issues_with_all_checked"] = 20
        self.assert_rejected_ledger(mutate, "all-ticked headline 8 -> 20")

    def test_mutation_queue_ref_dropped_without_omission(self):
        def mutate(led):
            q = next(x for x in led["next_work_queue"] if x["slice_id"] == "Q19")
            q["ac_refs"] = [r for r in q["ac_refs"] if r != "35:5"]
        self.assert_rejected_ledger(mutate, "Q19 dropped 35:5 without omitting it")

    def test_mutation_queue_omission_dropped(self):
        def mutate(led):
            q = next(x for x in led["next_work_queue"] if x["slice_id"] == "Q01")
            q["omitted_acs"] = q["omitted_acs"][:-1]
        self.assert_rejected_ledger(mutate, "Q01 omitted_acs lost a remainder id")

    def test_mutation_blocked_g1_exit_relabelled_zero_native(self):
        def mutate(led):
            q = next(x for x in led["next_work_queue"] if x["slice_id"] == "Q31")
            q["priority_class"] = "zero-native-verification"
            q["blocks_claim"] = ""
        self.assert_rejected_ledger(mutate, "Q31 relabelled zero-native")

    def test_mutation_zero_native_relabelled_blocked(self):
        def mutate(led):
            q = next(x for x in led["next_work_queue"] if x["slice_id"] == "Q02")
            q["priority_class"] = "blocked-native"
        self.assert_rejected_ledger(mutate, "Q02 relabelled blocked-native")

    def test_mutation_unknown_counts_key(self):
        def mutate(led):
            led["counts"]["bogus_metric"] = 1
        self.assert_rejected_ledger(mutate, "unknown counts key")

    def test_mutation_unknown_inputs_key(self):
        def mutate(led):
            led["inputs"]["bogus"] = 1
        self.assert_rejected_ledger(mutate, "unknown inputs key")

    def test_mutation_unknown_verdict_key(self):
        def mutate(led):
            led["verdict"]["bogus"] = 1
        self.assert_rejected_ledger(mutate, "unknown verdict key")

    def test_mutation_unknown_scope_key(self):
        def mutate(led):
            led["scope"]["bogus"] = 1
        self.assert_rejected_ledger(mutate, "unknown scope key")

    def test_mutation_head_rewritten(self):
        def mutate(led):
            led["head"] = "0" * 40
        self.assert_rejected_ledger(mutate, "ledger.head rewritten")

    def test_mutation_limitations_emptied(self):
        def mutate(led):
            led["limitations"] = []
        self.assert_rejected_ledger(mutate, "limitations emptied")

    def test_mutation_banned_ignored_evidence_reinserted(self):
        def mutate(led):
            led["inputs"]["cited_sources"].append("validation/gcs-handoff-20260909")
        self.assert_rejected_ledger(mutate, "ignored untracked evidence reinserted")

    def test_mutation_plan_doc_total_row_255_to_256(self):
        text = PLAN_DOC.read_text(encoding="utf-8").replace(
            "| **合计** |  | **255** |", "| **合计** |  | **256** |")
        self.assertFalse(accept_plan_doc(text), "plan-doc 255 -> 256 was accepted")

    def test_mutation_plan_doc_unchecked_150_to_100(self):
        text = PLAN_DOC.read_text(encoding="utf-8").replace(
            "| 未勾选 AC | **150** |", "| 未勾选 AC | **100** |")
        self.assertFalse(accept_plan_doc(text), "plan-doc 150 -> 100 was accepted")

    def test_mutation_plan_doc_drops_gap_issue_48(self):
        text = PLAN_DOC.read_text(encoding="utf-8").replace("#47、#48", "#47")
        self.assertFalse(accept_plan_doc(text), "plan-doc drop #48 was accepted")


class ExactSetsTests(unittest.TestCase):
    def test_exact_sets_match_literals(self):
        led = ledger()
        sets = led["exact_sets"]
        self.assertEqual(set(sets["checked"]), checked_ids(led))
        self.assertEqual(set(sets["unchecked"]), unchecked_ids(led))
        self.assertEqual(len(sets["checked"]), EXPECTED_AC_CHECKED)
        self.assertEqual(len(sets["unchecked"]), EXPECTED_AC_UNCHECKED)
        self.assertEqual(set(sets["closed_with_unchecked_issues"]), set(EXPECTED_CLOSED_UNCHECKED))
        self.assertEqual(set(sets["open_with_unchecked_issues"]), set(EXPECTED_OPEN_UNCHECKED))
        self.assertEqual(set(sets["closed_with_all_checked_issues"]), set(EXPECTED_CLOSED_ALL_CHECKED))
        self.assertEqual({(str(e["issue"]), o) for e in sets["ticked_but_drifted"]
                          for o in e["ordinals"]},
                         set(EXPECTED_DRIFTED_TICKED))

    def test_closed_state_never_implies_fulfilment(self):
        led = ledger()
        closed_gap = set(led["exact_sets"]["closed_with_unchecked_issues"])
        open_gap = set(led["exact_sets"]["open_with_unchecked_issues"])
        all_checked = set(led["exact_sets"]["closed_with_all_checked_issues"])
        for issue in led["issues"]:
            if issue["state"] == "CLOSED" and issue["unchecked"] > 0:
                self.assertIn(issue["number"], closed_gap)
                self.assertNotIn(issue["number"], all_checked)
            if issue["state"] == "OPEN":
                self.assertNotIn(issue["number"], closed_gap)
                self.assertNotIn(issue["number"], all_checked)
        for banned in ("accepted_issues", "reopened_issues", "fulfilled_issues"):
            self.assertNotIn(banned, led["exact_sets"])

    def test_gap_sets_are_disjoint_and_cover_every_gap(self):
        led = ledger()
        closed_gap = set(led["exact_sets"]["closed_with_unchecked_issues"])
        open_gap = set(led["exact_sets"]["open_with_unchecked_issues"])
        all_checked = set(led["exact_sets"]["closed_with_all_checked_issues"])
        self.assertEqual(closed_gap & open_gap, set())
        self.assertEqual(closed_gap | open_gap | all_checked, set(ISSUE_REGISTRY))
        declared = {i["number"] for i in led["issues"] if i["unchecked"] > 0}
        self.assertEqual(closed_gap | open_gap, declared)

    def test_non_acceptance_checkboxes_are_recorded_not_counted(self):
        led = ledger()
        non_ac = led["ambiguity"]["non_acceptance_checkboxes"]
        expected = []
        for issue in snapshot()["issues"]:
            for hit in extract_section_scoped(issue["body"])["outside_section"]:
                expected.append({
                    "issue": issue["number"], "line": hit["line"],
                    "checked": hit["checked"], "text": hit["text"],
                    "text_sha256": sha256_text(hit["text"]),
                    "reason": "checkbox outside every '## Acceptance criteria' section "
                              "(child-ticket container block), excluded from the AC universe",
                })
        self.assertEqual(non_ac, expected)
        self.assertEqual({e["issue"] for e in non_ac}, set(EXPECTED_NON_AC_ISSUES))
        ids = {r["id"] for r in ledger_ac_rows(led)}
        for entry in non_ac:
            self.assertNotIn(f"{entry['issue']}:{entry['line']}", ids)

    def test_ambiguity_section_has_no_unexplained_findings(self):
        led = ledger()
        amb = led["ambiguity"]
        self.assertEqual(set(amb.keys()), AMBIGUITY_KEYS)
        malformed = [{"issue": i["number"], **h} for i in snapshot()["issues"]
                     for h in find_malformed_checkboxes(i["body"])]
        self.assertEqual(malformed, [], "a malformed checkbox-like line exists")
        self.assertEqual(amb["malformed_checkbox_lines"], [])
        self.assertEqual(amb["empty_text_rows"], [])
        self.assertEqual(amb["issues_without_acceptance_heading"], [])
        non_cb = [{"issue": i["number"], "line": ln} for i in snapshot()["issues"]
                  for ln in find_non_checkbox_bracket_lines(i["body"])]
        self.assertEqual(amb["non_checkbox_list_bracket_lines"], non_cb)
        self.assertGreater(len(non_cb), 0, "link-list brackets must be recorded, not ignored")
        for row in ledger_ac_rows(led):
            self.assertTrue(row["text"])
            self.assertRegex(row["text_sha256"], r"^[0-9a-f]{64}$")


class NextWorkQueueTests(unittest.TestCase):
    def test_queue_schema_and_rank_sequence(self):
        queue = ledger()["next_work_queue"]
        self.assertGreaterEqual(len(queue), 1)
        self.assertEqual([q["rank"] for q in queue], list(range(1, len(queue) + 1)))
        ids = [q["slice_id"] for q in queue]
        self.assertEqual(len(ids), len(set(ids)), "duplicate queue slice ids")
        for q in queue:
            self.assertEqual(set(q.keys()), QUEUE_KEYS, q["slice_id"])

    def test_every_queue_row_cites_exact_ac_ids(self):
        led = ledger()
        valid = {r["id"] for r in ledger_ac_rows(led)}
        for q in led["next_work_queue"]:
            self.assertTrue(q["ac_refs"], f"{q['slice_id']} has no AC citation")
            for ref in q["ac_refs"]:
                self.assertIn(ref, valid, f"{q['slice_id']} cites unknown AC id {ref}")

    def test_every_queue_row_declares_its_omitted_acs(self):
        led = ledger()
        unchecked = unchecked_ids(led)
        for q in led["next_work_queue"]:
            refs = set(q["ac_refs"])
            omitted = q["omitted_acs"]
            self.assertEqual(len(omitted), len(set(omitted)), f"{q['slice_id']} duplicate omission")
            self.assertEqual(refs & set(omitted), set(), f"{q['slice_id']} both cites and omits")
            ref_issues = {int(r.split(":")[0]) for r in refs}
            for rid in omitted:
                self.assertIn(int(rid.split(":")[0]), ref_issues,
                              f"{q['slice_id']} omits an AC of an unreferenced issue")
                self.assertIn(rid, unchecked, f"{q['slice_id']} omits a non-unchecked AC {rid}")
            self.assertEqual(omitted, expected_omitted_acs(q, unchecked),
                             f"{q['slice_id']} omitted_acs is not the exact remainder")

    def test_every_queue_row_class_matches_literal_registry(self):
        queue = ledger()["next_work_queue"]
        self.assertEqual({q["slice_id"] for q in queue}, set(EXPECTED_QUEUE_CLASS))
        for q in queue:
            self.assertEqual(q["priority_class"], EXPECTED_QUEUE_CLASS[q["slice_id"]],
                             q["slice_id"])
            self.assertIn(q["priority_class"], ALLOWED_PRIORITY_CLASSES, q["slice_id"])
            if q["priority_class"].startswith("blocked-"):
                self.assertTrue(q["blocks_claim"], q["slice_id"])

    def test_queue_never_cites_a_checked_ac_except_drifted(self):
        led = ledger()
        done = checked_ids(led)
        drifted = {f"{n}:{i}" for n, i in EXPECTED_DRIFTED_TICKED}
        for q in led["next_work_queue"]:
            offenders = set(q["ac_refs"]) & done
            self.assertEqual(offenders - drifted, set(),
                             f"{q['slice_id']} cites an already-checked AC")
            for ref in offenders:
                self.assertIn(ref, drifted,
                              f"{q['slice_id']} cites {ref} without a drift record")

    def test_queue_priority_classes_are_known(self):
        for q in ledger()["next_work_queue"]:
            self.assertIn(q["priority_class"], ALLOWED_PRIORITY_CLASSES, q["slice_id"])

    def test_blocked_rows_name_their_blocker_and_zero_native_rows_do_not(self):
        for q in ledger()["next_work_queue"]:
            if q["priority_class"].startswith("blocked-"):
                self.assertTrue(q["blocks_claim"], f"{q['slice_id']} missing blocker claim")
            else:
                self.assertEqual(q["priority_class"][:11], "zero-native", q["slice_id"])

    def test_zero_native_rows_cite_resolvable_local_evidence(self):
        led = ledger()
        for q in led["next_work_queue"]:
            self.assertTrue(q["evidence"], f"{q['slice_id']} has no evidence")
            for rel in q["evidence"]:
                self.assertTrue((REPO / rel).exists(),
                                f"{q['slice_id']} evidence missing: {rel}")
            if q["priority_class"].startswith("zero-native"):
                for rel in q["evidence"]:
                    self.assertFalse(rel.startswith("validation/coordination/"),
                                     f"{q['slice_id']} cites advisory-only evidence")

    def test_every_issue_with_unchecked_acs_has_a_queue_row(self):
        led = ledger()
        gaps = {n for n in ISSUE_REGISTRY if registry_ac_checked(n) < registry_ac_total(n)}
        covered = {int(ref.split(":")[0]) for q in led["next_work_queue"] for ref in q["ac_refs"]}
        self.assertEqual(gaps - covered, set(), "unchecked issues with no queue row")
        self.assertIn(17, covered, "#17 drifted ticked rows must also be queued")

    def test_queue_rows_are_not_report_only(self):
        for q in ledger()["next_work_queue"]:
            self.assertTrue(q["closure_rule"].strip(), q["slice_id"])
            self.assertTrue(q["why"].strip(), q["slice_id"])
            self.assertNotEqual(q["closure_rule"].strip().lower(), "report", q["slice_id"])


class LocalEvidencePinsTests(unittest.TestCase):
    def test_cited_committed_evidence_pins_match_files(self):
        pins = ledger()["inputs"]["local_evidence_pins"]
        self.assertGreaterEqual(len(pins), 1)
        for rel, meta in pins.items():
            target = REPO / rel
            self.assertTrue(target.exists(), f"missing pinned evidence: {rel}")
            self.assertEqual(meta["sha256"], sha256_bytes(target.read_bytes()), rel)
            if meta["blob_sha1"] is not None:
                self.assertEqual(meta["blob_sha1"], git_blob_sha1(target.read_bytes()), rel)

    def test_cited_sources_exist(self):
        for rel in ledger()["inputs"]["cited_sources"]:
            self.assertTrue((REPO / rel).exists(), f"missing cited source: {rel}")
            self.assertNotIn(rel, BANNED_IGNORED_UNTRACKED_EVIDENCE, rel)
            self.assertFalse(path_is_ignored_untracked(rel),
                             f"cited source is git-ignored and untracked: {rel}")

    def test_queue_evidence_is_clean_checkout_reachable(self):
        for q in ledger()["next_work_queue"]:
            for rel in q["evidence"]:
                self.assertTrue((REPO / rel).exists(), f"{q['slice_id']} missing {rel}")
                self.assertNotIn(rel, BANNED_IGNORED_UNTRACKED_EVIDENCE, rel)
                self.assertFalse(path_is_ignored_untracked(rel),
                                 f"{q['slice_id']} evidence ignored+untracked: {rel}")
                if q["priority_class"].startswith("zero-native"):
                    self.assertFalse(rel.startswith("validation/coordination/"),
                                     f"{q['slice_id']} cites advisory-only evidence")

    def test_offline_declaration(self):
        led = ledger()
        self.assertEqual(led["inputs"]["test_runtime_dependencies"], [])
        self.assertFalse(led["verdict"]["network_used_during_tests"])
        self.assertTrue(led["verdict"]["snapshot_only"])

    def test_snapshot_is_the_only_test_time_input(self):
        """The suite must be runnable from the snapshot alone."""
        snap = snapshot()
        for issue in snap["issues"]:
            self.assertIn("body", issue)
            self.assertEqual(snap["issue_range"]["first"], ISSUE_FIRST)
            self.assertEqual(snap["issue_range"]["last"], ISSUE_LAST)
            self.assertEqual(snap["issue_range"]["count"], EXPECTED_ISSUE_COUNT)
            self.assertEqual(snap["issue_range"]["issue_sum"], EXPECTED_ISSUE_SUM)
        self.assertIn("gh issue list", " ".join(snap["source_commands"]))


class PlanDocTests(unittest.TestCase):
    def test_plan_doc_exists_and_states_no_acceptance(self):
        self.assertTrue(PLAN_DOC.exists())
        text = PLAN_DOC.read_text(encoding="utf-8")
        self.assertIn("not-closed", text)
        self.assertNotIn("Full = closed", text)
        self.assertIn("190", text)
        self.assertIn("150", text)
        self.assertIn("255", text)
        self.assertIn("65", text)
        self.assertIn("advisory", text)
        self.assertIn(EXPECTED_SNAPSHOT_REL, text)
        self.assertIn(EXPECTED_HEAD, text)
        self.assertTrue(accept_plan_doc(text), "plan doc failed the aggregate-row predicate")

    def test_plan_doc_names_every_gap_issue(self):
        text = PLAN_DOC.read_text(encoding="utf-8")
        for n in EXPECTED_CLOSED_UNCHECKED + EXPECTED_OPEN_UNCHECKED + (17,):
            self.assertIn(f"#{n}", text, f"plan doc omits #{n}")
        self.assertIn("#47、#48", text)

    def test_plan_doc_states_the_issue_20_section_distinction(self):
        text = PLAN_DOC.read_text(encoding="utf-8")
        self.assertIn("#20", text)
        self.assertIn("容器", text)

    def test_plan_doc_aggregate_rows_match_literals(self):
        text = PLAN_DOC.read_text(encoding="utf-8")
        total = re.search(
            r"^\|\s*\*\*合计\*\*\s*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|",
            text, re.M,
        )
        self.assertIsNotNone(total)
        got = [int(re.sub(r"[^0-9]", "", g)) for g in total.groups()]
        self.assertEqual(got, [255, 40, 190, 40, 150, 65])
        self.assertIn("| 未勾选 AC | **150** |", text)
        self.assertIn("| CLOSED 且仍有未勾选 AC | 22 |", text)
        self.assertIn("| OPEN 且仍有未勾选 AC | 8 |", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    print(json.dumps({
        "suite": "test_full_original_ac_gap_ledger",
        "snapshot": str(SNAPSHOT.relative_to(REPO)),
        "ledger": str(LEDGER.relative_to(REPO)),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "verdict": "PASS" if result.wasSuccessful() else "FAIL",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "network_used": False,
    }, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
