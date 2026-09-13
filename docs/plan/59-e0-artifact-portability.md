# #59 E0 private artifact portability

The tracked source-to-slot manifest records the exact identity of the two
model inputs, but the model bytes remain private and are ignored by Git. A
strict validation therefore needs those bytes from an owned local source:

| logical manifest path | identity |
| --- | --- |
| `validation/model-reference-readiness-20260909/attempt-07/staged-model/MulticopterModel.zip` | SHA-256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`; member `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp`; member SHA-256 `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019` |
| `validation/model-reference-readiness-20260909/attempt-07/staged-model/Exp1_MinModelTemp.slx` | SHA-256 `c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392` |

The default validator resolves these paths below the repository and remains
strict. A clean checkout can use an external private mirror with
`--artifact-root`; the mirror must reproduce the declared relative paths:

```text
<artifact-root>/validation/model-reference-readiness-20260909/attempt-07/staged-model/MulticopterModel.zip
<artifact-root>/validation/model-reference-readiness-20260909/attempt-07/staged-model/Exp1_MinModelTemp.slx
```

For example, after placing the private files under that mirror, run:

```powershell
python -B tools/validate_e0_source_to_slot_manifest.py --artifact-root C:/private/wksim-models
```

The external root changes only the lookup root. The validator still checks the
manifest's frozen path and SHA-256 values, hashes the complete ZIP, hashes the
named ZIP member without extraction, and hashes the SLX bytes. A missing file,
changed file, changed member path, or changed member bytes remains a strict
failure. The private files must never be committed merely to make this check
pass.

Without the private artifacts, a clean checkout can inspect the tracked
manifest and its declared identities, but it cannot perform strict byte
verification. This check is provenance evidence only; the manifest remains
unresolved and the result cannot establish #59 G6 or physical-accuracy
acceptance.
