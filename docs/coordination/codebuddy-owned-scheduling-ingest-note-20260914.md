# Ingest note: owned-scheduling 历史语境候选 — 2026-09-14

- 类型：离线历史语境摄入（historical-context ingest）。**不是**验收、不是实现、不执行/启动任何调度或 native。
- 权威 checkout/HEAD：`31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（Windows 主检出 `C:/Users/PC/Documents/odid编译/wksim`，开工时 `git rev-parse HEAD` 实测一致）。
- 架构基线祖先检查：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0（实际核验）。
- 工作类别：纯离线文档/纯测试写入。未跑 native/模型/MATLAB/ROS/DDS/SITL/FC/UE/构建，未用网络，未 Git mutation（无 add/reset/clean/commit/push/fetch），未触碰 #83（已 CLOSED/PASS，永不重跑）与 #84/G6/Full 等未完成项，未触碰其它在途批次文件。

## 1. 五份来源（tracked @ 31e5b65f，工作树字节 == HEAD blob，实测）

| 文件 | SHA256 | 字节数 |
|---|---|---|
| docs/coordination/codebuddy-owned-scheduling-review-20260913.md | `e7641f65b15d0ef2ea7e865c57ceddffb53ee6e4eefecc74adea63d2138592ce` | 5598 |
| docs/coordination/codebuddy-scheduling-comparison-review-20260913.md | `2bc26aaf6a87ed2ddcde746eb06e5cc02c21c111502d74396e4f8c2d1654bdab` | 4878 |
| docs/coordination/owned-scheduling-snapshot-20260913.md | `b4f1f5323e2502028f7296d5b158f9b07ec387da6e3b0124cfdc7465e56dd069` | 7470 |
| docs/coordination/owned-scheduling-comparison-20260913.md | `0dfd79adfaa9d6b25302e5304290dd337431214e8f9fb0c6817848164010e04c` | 6365 |
| docs/coordination/owned-scheduling-e2e-20260913.md | `fc7a74d7b325d691498fd0eed187f1d4a9afab907e097bf6cdeda8b56076247f` | 6709 |

五份文件均 tracked 且工作树与 HEAD blob 字节一致。**全部按"已被取代的历史语境"对待**（见 §4）。

## 2. Tracked 证据锚点（@ 31e5b65f，工作树字节 == HEAD blob，实测）

| 锚点 | SHA256 | 字节数 | 与来源声明的关系 |
|---|---|---|---|
| tools/capture_owned_scheduling.py | `a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e` | 20901 | 与 review §1、e2e §4 pin **一致** |
| validation/test_owned_scheduling.py | `a0e747d3c6fa93f4f68cb08591d8d83708164b8fef261136b042abc908e71319` | 22401 | 与 review §1 pin **一致** |
| tools/compare_owned_scheduling.py（当前） | `13a61a7ffd92880571613c69d3d31736f1982e75ff03b365e2602338c928ec6f` | 21412 | 与 snapshot 文档收口补记一致；**取代** comparison-review pin |
| validation/test_compare_owned_scheduling.py（当前） | `a8eb584df5c86112fa8f39dff4869f4d2e0baa652a56c8ff3164a12b3cf12ca9` | 21061 | **取代** comparison-review pin（见 §4 限制） |
| validation/coordination/owned-scheduling-e2e-20260913/source-compare-v1.py | `033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d` | 21218 | 历史比较器原字节，与 comparison-review pin **逐字节一致** |
| validation/coordination/owned-scheduling-e2e-20260913/source-run-e2e-v1.py | `b2e691cd8da081e7e93087d8158098dff6905f101922bd873fb344b3f49b9ef2` | 8226 | 与 e2e 文档 §4 pin **一致** |

语义锚点（当前 tracked 字节 grep 实证）：capture `:458` `performance_verdict="not_evaluated"`、`:462` `open("x")` 独占输出、`:327` `read_bytes()` 原始字节哈希、`kernel_prio` 改名（`:105,222-225`）、`sched_schedstats_disabled/unreadable`（`:203,205`）、`thread_identity_changed`（`:276-277`）、`_identity_problem`（`:380,405,415`）；compare `:140` `_as_int`、`:160` `invalid_counter_value`、`:121` `host_sched_schedstats_not_enabled(...)`、`:126` `runqueue_counters_valid is True`。测试函数定义计数（当前字节）：`test_owned_scheduling.py` 18 个（pytest parametrize 展开后为 review 报告的 31 collected）、`test_compare_owned_scheduling.py` 23 个（对应 40 collected）。

## 3. Tracked 飞行快照（@ 31e5b65f，flight/ 目录）

两个 run 目录的 `flight/owned-scheduling-before/after.json` 均为真实 schema `wksim.owned-scheduling-snapshot.v1`，`sampler_sha256 == a3f3badd…`（与 capture 工具一致），11 个 role 全部 `captured`，`host.sched_schedstats == "0"`（字符串，runqueue/timeslice 无效测量），`CLK_TCK == 100`，`performance_verdict == "not_evaluated"`：

| run | run_id | boot_id | children.sha256 | before/after 快照字节 SHA（== result.json 记录值，实测匹配） |
|---|---|---|---|---|
| last-callbacks-run-20260913-01 | joint-public-flight-5lfbcy43 | `2e7caa0c-f041-426f-a550-50acd12125c5` | `268825bb27300713a3800a6f057fd0cfc78a9f518a70981ccae2037580b6b757` | before `4647d5a2a6711839db813ba84bbeb9df5abf5d30796f3f38a0098f835736d4e7`（228813B）/ after `7cf3c046aecf5bde0da9558f65daf3bf3d07aa524cbf21adb2f16989e020c5cb`（331637B） |
| manager99-run-20260913-01 | joint-public-flight-x39qjvkw | `5906186e-8181-42ff-8c56-d8ec2a26bd62` | `8ec3f5803cb3af61f56966352409ff65215ef21f0900962d531f54f932b594e4` | before `e9bed5bc0f590ab743a7ca05cb5f63c3177ecb703d746cb80452d36179aa396f`（228656B）/ after `699b4474b287d7815fc9d65092acc501064fdb4250167f693c97d8446ea8c821`（331602B） |

两 run 的 `result.json.owned_scheduling` 均 `classification="diagnostic_only"`、`full_acceptance=false`、`initialized=true`，且 before/after 记录的 sha256 与 tracked 快照原始字节逐一匹配（实测）。两 run 的 `flight_completed=false`、`error=RateUnmet('rate_unmet/resource_insufficient')`。

冻结门延续（仅重申，不在本批改动或重验）：`1ms` tick / native 屏障 / `4tick` 组 / 无追赶 / `100ms` 晚限 / 完整滑窗 / 原物理与身份门（见 short-cycle-goal.md、module-delivery-policy-20260912.md 规则 13）。

## 4. Supersession 与负面声明边界（本批最重要）

1. **五份来源全部是 2026-09-13 历史语境**（当时 HEAD 为 `820f532`，当前 HEAD 为 `31e5b65f`）。它们**不**证明当前 HEAD 的任何验收状态。
2. **比较器已被取代**：comparison-review pin 的 `033d8af8…`（21218B）是历史 v1 字节；当前 tracked 比较器为 `13a61a7f…`（21412B），由 owned-scheduling-comparison-20260913.md 的"主会话收口补记"记录（新增 bool/字符串/浮点/负原始计数 → null + `invalid_counter_value` 保护；runqueue 有效标志仅接受 True）。历史字节完整保存在 `source-compare-v1.py`，旧证据 pin 不改写。
3. **比较器测试 pin 不可锚定**：comparison-review pin 的 `validation/test_compare_owned_scheduling.py = 20cc459052c2cf8d860e2c1583334e583abd3b95c3d022a8a0795580ab8642fe`（19740B）**在当前 tracked 树中不存在对应字节副本**；当前 tracked 测试为 `a8eb584d…`（21061B）。因此该历史 pin 只能作为文档声明，无法以 tracked 字节复核——这是本批明确的已记录限制，不构成失败，但**不得**把 19740B/20cc4590 当作当前文件事实。
4. **禁止晋升/负面声明**（对两 run 快照与 e2e 同样适用）：
   - 不得宣称当前 acceptance、no-promotion 判定、G6 PASS、Full PASS 或任何 MIXED 正式通过；`#84`/G6/Full 未完成，正式 mixed 证据集仍为空。
   - 不得把 `diagnostic_only` / `full_acceptance=false` / `performance_verdict=not_evaluated` / `attribution=not_evaluated` 改写成任何 pass/fail 或性能结论。
   - 两 run 均 `flight_completed=false`（RateUnmet）；不得据此宣称修复、不做因果归因（short-cycle-goal.md 同款约束）。
   - e2e 烟测目标是普通 Python verifier/spinner，**不是** SITL/模型/native 行为证据；`sched_schedstats=0` 时 runqueue/timeslice 为 null+原因，**不得用 0 证明"无 runqueue 等待"**；`kernel_prio` 不是 RT priority，不得与 runner FIFO 40/49 直接比较。
   - 历史 tail 数值（如 57419470ns/54569053ns 等）属于 2026-09-13 场次，**不得转移**到当前 HEAD；向当前 HEAD 转移任何历史证据都需要显式 tracked 身份链（commit 祖先 + 字节 SHA + run 目录逐字节匹配）。
   - `#83` 已 CLOSED/PASS，永不重跑；本批与它无关。
5. **e2e 复跑规则**（保留）：复跑必须给尚不存在的新目录（原子 `os.mkdir` 独占创建，先拒后启）；旧 `owned-scheduling-e2e-20260913/` 为只读历史。

## 5. 排除数据（本批未读/未用/未改，归各自所有者）

- `docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`（既有他方修改，保留原样）；
- `docs/coordination/rolling-six-plan-20260912.md`、`docs/coordination/claude-native-wait-next-probe.md`、`validation/_probe_delivery_contract.py`、`%TEMP%audit26-report.json`；
- 全部 failed independent-review `-01` 目录；其它在途批次产物（gc-freeze、module-review、omp-*、audit-matrix 等未跟踪文件）；
- 未运行旧测试套件、未运行 e2e、未做任何构建/运行时操作。

## 6. Drift / 重跑规则

- 本批产物锚定**绝对提交** `31e5b65f…`（不是浮动的 HEAD）；内容断言一律取该提交的字节，HEAD 漂移不改变断言对象。
- 配套测试 `validation/test_owned_scheduling_context.py` 的显式 drift 策略：
  - 当前 HEAD == `31e5b65f…` → 断言正常执行；
  - 当前 HEAD ≠ `31e5b65f…` 且该提交仍可达 → HEAD 相关断言 **skip**（带原因），锚定提交上的内容断言照常执行；
  - 锚定提交不可达（如历史被重写/浅克隆）→ 内容断言 **skip**（fail-safe：不猜测、不降级为通过）；
  - 任何字节/hash/语义锚点不匹配 → **FAIL**（真实漂移，必须上报）。
- 两候选文件均为新增 tracked 候选：`docs/` 之一可直接正常 stage；`validation/*` 受 `.gitignore` 忽略，仅主会话可后续 `git add -f` 精确暂存。测试在真实 index 与 repo 外部 `GIT_INDEX_FILE` 临时 index 两种模式下均可运行（staged 模式下额外断言候选已入外部 index 且 blob 哈希等于工作树字节）。
- 失败原件不覆盖、已通过内容不重跑；重跑本批测试仅做只读断言，无副作用。

## 7. 提议候选集（恰好两路径，无其它）

1. `docs/coordination/codebuddy-owned-scheduling-ingest-note-20260914.md`（本文件）
2. `validation/test_owned_scheduling_context.py`（离线确定性 unittest，配套 §6 drift 策略）

不创建 manifest、不创建 review 目录；独立审查者后续自建。SHA/字节数见 §8 交付回执。

## 8. 交付回执（占位：由本批执行记录填写）

- 注：最终 SHA/字节数/测试计数以本批最终报告为准；测试对两候选文件的存在性与（staged 模式下）index 一致性做断言，对测试文件自身不做自哈希（自引用不可行）。
