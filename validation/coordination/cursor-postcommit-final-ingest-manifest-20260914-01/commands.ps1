# commands.ps1
# Suggested postcommit evidence ingest commands. THIS TASK DID NOT EXECUTE THEM.
# A later owner must separately authorize any real add/commit. No push.
# Forbidden: git add ., git add -A, directory add, wildcards, reset, clean,
# checkout, commit, push, rebase, force-push.
# .gitignore:53 /validation/*/ makes every path ignored; each add must be -f.
# Sequence: HEAD pin -> index-empty guard -> path-set existence check ->
# per-path git add -f -- -> staged-set/count compare.
# The 20260914-01 private-index rehearsal verified the draft 33-path set only.
# It does not verify this 42-path set.

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'

$pinned = '59d8da51b4c31b6aa050929ebbe81ccc357acfb5'
$head = (git rev-parse HEAD).Trim()
if ($head -ne $pinned) { throw "HEAD is $head, expected $pinned" }

$cached = @(git -c core.quotepath=false diff --cached --name-only --)
if ($cached.Count -ne 0) { throw "pre-ingest index-empty-guard failed: $($cached -join ',')" }

$expected = @(
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/commands.ps1'
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/exact-paths.txt'
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/path-hashes.json'
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane1-fast-independent-review-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane1-fast-independent-review-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/review.md'
  'validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/SHA256SUMS'
  'validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/review.json'
  'validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/review.md'
)
if ($expected.Count -ne 42) { throw "expected path count is $($expected.Count), want 42" }
$dup = @($expected | Group-Object | Where-Object { $_.Count -gt 1 })
if ($dup.Count -ne 0) { throw "duplicate expected paths: $($dup.Name -join ',')" }

$manifest = Get-Content -LiteralPath 'validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/exact-paths.txt'
if (@($manifest).Count -ne 42) { throw "exact-paths.txt count is $(@($manifest).Count), want 42" }
$missingManifest = Compare-Object -ReferenceObject $expected -DifferenceObject @($manifest) -PassThru
if ($missingManifest) { throw "exact-paths.txt set mismatch: $($missingManifest -join ',')" }

foreach ($p in $expected) {
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "missing file: $p" }
}

git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/commands.ps1
git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/exact-paths.txt
git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/path-hashes.json
git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane1-fast-independent-review-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane1-fast-independent-review-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane1-finalization-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane2-autocrlf-rerun-independent-review-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/review.md
git add -f -- validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/SHA256SUMS
git add -f -- validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/review.json
git add -f -- validation/coordination/cursor-postcommit-receipt-content-audit-20260914-01/review.md

$staged = @(git -c core.quotepath=false diff --cached --name-only --)
if ($staged.Count -ne 42) { throw "staged count is $($staged.Count), want 42" }
$onlyStaged = Compare-Object -ReferenceObject $expected -DifferenceObject $staged | Where-Object { $_.SideIndicator -eq '=>' }
$onlyExpected = Compare-Object -ReferenceObject $expected -DifferenceObject $staged | Where-Object { $_.SideIndicator -eq '<=' }
if ($onlyStaged -or $onlyExpected) {
  throw "staged set mismatch. extra=$($onlyStaged.InputObject -join ',') missing=$($onlyExpected.InputObject -join ',')"
}

Write-Host 'SUGGESTED ingest path-set and staged-cache checks passed. Not a commit.'
