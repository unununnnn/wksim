# DS-C · ds-scene-frontier-20260912 历史语境绑定与取代登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时 HEAD `9c581ad5b2e316904c9ef53e8543c5a6f413d6f9`（已验证 `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0）。

## 0. 本文件的地位

本文件只做两件事：把下述历史文件与已入库伴随测试**按字节绑定**为历史语境，并登记其后的取代事实。它自身不构成 #29、#102 或 #9 的验收、批准、收口或复核记录，不构成任何实时票面状态裁定，也不授予任何原生物理/构建/联调执行许可；被绑定的历史文件同样**不再**构成这些。一切"当前是否满足/是否可关闭"的判定必须由当前权威（主代理/主会话/人类裁决）基于**当下**的工件重新作出。

## 1. 历史语境绑定（字节级）

| 项 | 被绑定文件 | SHA256 | 大小 | 性质 |
| --- | --- | --- | --- | --- |
| 1 | `docs/coordination/ds-scene-frontier-20260912.md` | `9922942f3e13d712d02c050e62825dcc004f9cac41205de8b169b83c232a557e` | 7691 bytes | **历史语境（historical context only）**。2026-09-12 DS-C 场景反馈前沿单文件交付：#29 原 AC 剩余缺口离线核对记录 |
| 2 | `validation/test_scene_frontier_contract.py` | `3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2` | 6364 bytes | **已入库伴随测试（tracked）**，提交 `cf509f5361f468e78bb81e47b3992ddf7db02957`（"Add scene frontier contract checks"）。写作时验证：`git show cf509f53:validation/test_scene_frontier_contract.py` 重哈希 == 上列值 == 工作树，`git status` 对该文件干净 |

**非权威声明**：历史文件 §二票面表、§三缺口表、"当前状态"等表述均是**写作时点快照**，不是当前的权威、批准、验收或收口状态。引用它只能作为"当时观察到了什么"，不能作为"现在是什么状态"。

## 2. 经本次复核仍然稳定的事实（read-only 重算，HEAD `9c581ad5`）

1. **绑定哈希**：两文件 SHA256 重算与 §1 一致；历史文件大小 7691 bytes。
2. **清单状态未漂移**：`docs/plan/29-terrain-evidence-manifest.json` 仍为 `status=partial_open`、`acceptance=false`、`blocking_issue=9`，且声明三项 `unproven_boundaries`（`missing_real_ue_physics_colocation` 真实 UE5.5 显示与权威物理同置、`missing_fc_closed_loop` probe native I/O 为确定性 stub 非 FC 闭环、`missing_slope_contact_force_dynamics` 坡度/接触力/刚度/阻尼/摩擦/侧碰/动态对象）。该清单最后触及提交为 `c3f0d319`（2026-09-12）；`git log --since=2026-09-12` 对清单、两份契约、三个 runtime 模块与 probe 工具均为空——历史文件的"当前有效状态"表述在本 HEAD 仍成立。
3. **三层场景身份**：`visual_static_scene` = `static-plane-box-v1` / `60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514` @[2.0, 0.0, 0.5]；`real_terrain_scene` = `static-plane-box-v1-real-tick0` / `4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300` @[0.0, 0.0, 0.5]；planner 第三层 `EXPECTED_SCENE_HASH = 40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba`（`Simulator/wksim_runtime/planner_scene_binding.py:77`）。运行时接缝 `Simulator/wksim_runtime/contact_observer.py:26` 的 `FROZEN_SCENE_SHA256` 绑定冻结视觉夹具 `60ae5097…`，而非 probe 身份。`29-102-scene-binding-contract.md:60-62` 的 probe 措辞与历史文件引用逐字一致。
4. **强制离线测试**：`python -B -m unittest validation.test_scene_frontier_contract -v` 重跑 **Ran 6 tests, OK, 0 failures, 0 errors, exit 0**（6/6），含 probe 身份拒绝与 foreign-epoch fail-closed 冻结两处真实接口回归。
5. **夹具存在且被跟踪**：`validation/lunar-29-static-contact/`、`validation/lunar-29-live-contact/`、`validation/lunar-29-terrain-reset-c8f05c6e/`（位于 `validation/` 下，非 `validation/coordination/`）。

## 3. 取代登记（supersessions）——以下各项取代历史文件的对应表述

1. **零出现断言已被取代**：历史文件 §四.1 "全仓 `validation/*.py` 中 `4889e2ea` 与 `40ee9281` 零出现"（以及 `observers=` 零出现的同节表述）仅对**写作时点的既有测试**成立。本 HEAD 下该断言已不成立：`validation/test_scene_frontier_contract.py`（本切片伴随测试，已入库）本身含两值，另有 `validation/coordination/ds-g3-closure-frontier-20260913-01/check_g3_closure.py`、`validation/coordination/omp-g4-terrain-readiness-20260913-01/probe.py`、`validation/coordination/deepseek-102-residual-20260914-01/probe.py` 共 4 个 `validation/*.py` 文件含之。引用时必须保留"写作时点既有测试"的历史辖域，不得当作当前树事实。
2. **§二 票面状态表为 2026-09-12 快照**：表中 #29 OPEN（原 AC 5 条未勾）、#79/#80/#81 CLOSED（2026-09-10）、#17 CLOSED（2026-09-05）、#23 CLOSED（2026-09-09，R1 边界保留）、#9 OPEN（ABI NO-GO）均为**当日实测快照**，本文件未做任何实时查询、不认可其为 timeless 事实。任何"当前票面状态"引用需实时重查或由当前权威裁定。
3. **两文件交付状态不对称**：历史文件 §五 自述交付 2 个文件。现状：伴随测试已入库（`cf509f53`，工作树干净），而历史文件 `docs/coordination/ds-scene-frontier-20260912.md` 本身仍为未跟踪文件。此不对称是当前事实登记，不是缺陷裁定，也不是任何提交流已完成或应发生的指示。

**取代路径**：§四.1 零出现断言 → 本节第 1 项（4 文件清单）；§二 票面表 → 本节第 2 项（快照辖域）；§五 交付自述 → 本节第 3 项。

## 4. 必须命名的跟踪锚点（tracked anchors）

后续任何引用、复核或 ingest 清单必须以下列**已跟踪**工件为准（均为本 HEAD 实测）：

- `docs/plan/29-terrain-evidence-manifest.json`（最后触及 `c3f0d319`，2026-09-12）
- `docs/plan/29-contact-observer-contract.md`
- `docs/plan/29-102-scene-binding-contract.md`（probe 措辞在 60-62 行）
- `docs/plan/29-terrain-closure-report.md`
- `docs/plan/9-vendor-abi-defer-boundary.json`（`official_source_unavailable` / `available_and_reviewed_in_source` / defer 边界，对应 #9 ABI NO-GO 语境）
- `Simulator/wksim_runtime/planner_scene_binding.py`（`:64-65` `LEGACY_SCENE_ID`/`LEGACY_SCENE_HASH`、`:77` `EXPECTED_SCENE_HASH`、`:1072` `EGO_SINGLE_BOX_BINDING`）
- `Simulator/wksim_runtime/contact_observer.py`（`:26` `FROZEN_SCENE_SHA256`）
- `Simulator/wksim_runtime/terrain_feedback.py`（epoch/observers 注入与 freeze 语义）
- `tools/probe_joint_terrain_feedback.py`
- `validation/test_scene_frontier_contract.py` @ `cf509f5361f468e78bb81e47b3992ddf7db02957`
- `validation/test_planner_scene_binding.py`、`validation/test_audit_29_terrain_evidence.py`
- `validation/lunar-29-static-contact/`、`validation/lunar-29-live-contact/`、`validation/lunar-29-terrain-reset-c8f05c6e/`

## 5. 后续离线测试 seam（offline-test seam）

后续任何离线复核可按以下步骤重演本文件的绑定与取代判定，无需网络、无需执行模型/构建/UE/SITL/FC：

1. **字节绑定**：`sha256sum docs/coordination/ds-scene-frontier-20260912.md` == `9922942f…a557e` 且 size == 7691；`git show cf509f5361f468e78bb81e47b3992ddf7db02957:validation/test_scene_frontier_contract.py | sha256sum` == `3f593d8f…6c3de2` 且与工作树一致。若不等，则绑定失效，需重新建立。
2. **清单状态**：重读清单，`status=partial_open`、`acceptance=false`、`blocking_issue=9`、三项 `unproven_boundaries` 在场。
3. **身份三层**：重算/重读 §2.3 所列两处 runtime 常量与两份身份，三层两两不等。
4. **强制测试**：`python -B -m unittest validation.test_scene_frontier_contract -v` == 6/6 OK exit 0。
5. **取代事实**：`grep -rl "4889e2ea\|40ee9281" validation/ --include="*.py"` 至少命中本文件 §3.1 所列 4 个文件；`git status --porcelain -- validation/test_scene_frontier_contract.py` 为空。
6. **祖先关系**：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` exit 0。
7. **非权威措辞检查**：本文件与被绑定文件不得在任何后续文档中被表述为 "acceptance"、"approval"、"closure"、"closes #29/#9/#102"、" Grants native execution permission" 等权威措辞；票面状态只能以"2026-09-12 快照，需实时重查"的措辞引用。

任何一步失败均表示本登记过期，应以当时权威的工件重建登记，而不是沿用本文件结论。

## 6. 边界

- 本文件为只读核验产物：未修改被绑定文件、伴随测试、清单、契约或任何既有共享文件；未运行模型、构建、UE、SITL、FC、ROS、DDS 或 MATLAB；未读厂商源码字节；未查询实时 GitHub 状态（§3.2 刻意如此，以免快照被当作 timeless）。
- 未执行 `git add/commit/push`；未触碰 `docs/Prometheus.gitmodules.reference` 与 `validation/coordination/short-cycle-dispatches.json`；未运行 #83 或任何 #83 相关工作流。
- 本文件创建后即成为静态工件；其 SHA256 与大小在交付报告中给出，后续以此检测自身是否被篡改。
