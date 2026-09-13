# Three independent DeepSeek deliveries

All three fresh tasks used the implemented architecture on `main` with
`f333316` verified as an ancestor. The owners delivered separate file sets;
the main coordinator reviewed the changes and ran the combined checks.

| Module | Result | Validation |
| --- | --- | --- |
| Experiment/deployment input identity | Parsed semantics and SHA256 come from the same read. Resolved plans own their input values. Aliases of one file cannot serve both roles; changed inputs are refused before execution. | Mutation, deletion, alias/hard-link, invalid input and existing-output cases; actual execution is mocked. |
| Ackermann response | A speed step cannot overshoot its current target; a clipped step reports its actual acceleration. The named-actuator and SI/NED/FRD interfaces remain in their existing modules. | Original peak 5.0010000000000785 m/s becomes 5.0 m/s. An independent frozen-source comparison found 4,000 default-parameter states, each with 17 doubles, bit-identical. |
| Offline replay | Both initial read and stability re-read enforce the byte cap on consumed data. One bytearray replaces per-chunk retention; oversize input is refused rather than silently truncated. | Size/growth/replacement/short-read cases, SHA and ordering checks, and actual Linux symlink coverage. |

The [main Linux receipt](../validation/coordination/three-deepseek-main-acceptance-20260913-01/linux-receipt.json)
records 64 successful checks with unchanged tested sources and process cleanup.
Windows ran the same 64 checks: 63 passed and the privilege-dependent symlink
case was skipped. Linux covered that case. The default-model comparison is
recorded [separately](../validation/coordination/three-deepseek-main-acceptance-20260913-01/ackermann-independent.json).

The acceleration test allows only calculated binary64 multiply/add/subtract/
divide roundoff when reconstructing a derivative from two stored speeds.
The speed and returned acceleration bounds remain strict. This does not set
or relax a G6 physical error budget.

The tasks did not run SITL, UE, hardware or vendor models. These component
checks do not complete G4/#46, establish new physical accuracy, or transfer
old flight PASS results to the new architecture candidate. Deployment and
affected end-to-end acceptance remain separate.

Exact delegation handles and file ownership are in the
[dispatch record](../validation/coordination/three-deepseek-other-20260913-01.json).
