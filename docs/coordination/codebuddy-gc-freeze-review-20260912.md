# C1 `--manager-gc-freeze` 独立复核（A 实现 + OMP 比较器合同）

只读复核；唯一写入本文件。未运行 native/SITL/模型/构建，未改实现，未提交 Git。允许的轻量纯测试与
单文件只读复算已执行并注明。

## 0. 复核对象与 SHA 快照

A 在 22:33:39 / 22:34:14 两次改动后，三文件在 22:36:10 至 22:45（多次重算）保持不变；本报告只对该
快照负责，之后的任何 diff 未审：

| 文件 | SHA256 |
|---|---|
| `tools/manager_gc_candidate.py` | `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66` |
| `validation/test_manager_gc_candidate.py` | `637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad` |
| `tools/run_joint_flight.py` | `fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246` |

**路径更正（不推广旧 review）**：C1 落在 `tools/run_joint_flight.py`（PV/33-rate-profile 的 supervisor
进程），**不是** `Simulator/wksim_runtime/joint_runtime.py`。此前设计复核里对 joint_runtime 清理链的
行号结论不适用于本候选；下文全部按 `fd0b7ee6` 的真实 runner 重新核对。

## 1. 主会话两缺陷：已在快照中修复（逐行）

- **D1 泄漏（freeze 成功后 `_snapshot(after)` 抛错）**：`manager_gc_candidate.py:200-205`——
  `self._gc.freeze()` 返回后**立即** `self._we_froze = True`，之后才 `_snapshot("after")`；`restore()`
  在 `:223-228` 只要 `_we_froze` 为真就 unfreeze。抛错时 runner 的 finally 仍会释放。✓
- **D2 arm→prepare 外部 GC 漂移**：`_revalidate()`（`:151-183`）在 `prepare()` `:196` 冻结前重查
  `isenabled` / `get_freeze_count()==0` / thresholds 与 arm 时一致；任一漂移在**任何 mutation 之前**
  拒绝。✓
- 残余（可接受，记录在案）：`freeze()`/`collect()` 自身抛错时 `_we_froze` 仍 False，restore 为
  noop，无泄漏；restore 内 `get_freeze_count()` 抛错会留下已冻结图（真实 gc 不会发生），被 runner
  记为 `manager_gc_candidate_error`。

## 2. runner 清理链：四项要求逐项核对（`run_joint_flight.py` @ `fd0b7ee6`）

1. **freeze 早于 physics.connect / 首 anchor**：`:888-905` 完成 task `initialized` 与 model tick-0
   身份/快照校验（含 `clock.tick!=0` 拒绝）→ `:906-907` `manager_gc.prepare(...)` → `:908`
   `physics.connect()` → 首个 anchor 在 `:917-918`（`rate.reanchor`）。次序满足且 tick-0 已验证。✓
2. **restore 在所有 native cleanup 之后、且 cleanup 出错仍执行**：`try` 在 `:466`，`with ExitStack`
   在 `:791`（try 内），except 在 `:1041/:1043`、finally 在 `:1048`；finally 内
   `try: cleanup_children(...)`（`:1049-1050`，终止/回收全部子进程）`... finally: restore()`
   （`:1062-1073`）。cleanup 抛错时内层 finally 仍 restore；restore 自身 `except BaseException`
   只记录错误不阻断。其后只有 `unowned_ap_after`/`source_unchanged` 校验。✓
3. **GC callback 去除先于日志关闭**：`ExitStack` 在 except/finally 之前展开。注册序
   `rate_log(801)→wire(812)→clock_log(813)→JointPhysics{socket,listener,gc.callback}(818)→
   lifecycle(826)`，LIFO 展开序 `lifecycle→gc.callbacks.remove→sockets→clock_log→wire→rate_log→…`，
   故 callback 一定先移除、不可能向已关流写。✓（注意本 runner 的 `rate_log` 也在 ExitStack 内，
   与 joint_runtime 路径不同。）
4. **不改 enabled/threshold**：全文件 GC 调用仅
   `isenabled/get_freeze_count/get_count/get_threshold/get_stats/collect/freeze/unfreeze`；无
   `gc.disable`/`set_threshold`。默认（无 flag）`manager_gc is None`，不读不写 GC，sources 不加
   candidate 模块；flag 经 `getattr(args,'manager_gc_freeze',False)` 仅显式开启，且
   `parser.error` 限定 PV/MIXED。✓

## 3. **新缺陷 D3（未修）**：A 的产物无法通过 OMP 比较器的已声明合同

- 合同声明位置：`docs/plan/33-rate-measured-candidate-20260912.md` §6 与
  `tools/compare_joint_gc_diagnostics.py:35,73,251-278`。要求候选目录存在
  **`gc-freeze.json`**（`resolve_inputs` `:73`；或用 `--candidate-gc-freeze` 显式覆盖），其字段：
  `schema=="wksim.joint-gc-freeze.v1"`、`enabled is True`、
  `freeze_calls == {gc.collect, gc.freeze}`、`gc_disabled is False`、`threshold_adjusted is False`、
  `restore.restored is True`、`restore.calls ⊇ {gc.unfreeze}`。
- A 现状：`tools/run_joint_flight.py:1071` 保存的是 `manager-gc-candidate.json`（**文件名不同**）；
  `ManagerGCFreeze.report()`（`:248-273`）只含 `module/classification/candidate/performance_pass/
  enabled/.../restore{freeze_count_before_unfreeze,freeze_count_after_unfreeze,
  expected_original_freeze_count,restored_to_original}/events`，**缺** `schema`、`freeze_calls`、
  `gc_disabled`、`threshold_adjusted`、`restore.restored`、`restore.calls`。
- 影响（已按代码路径核对）：默认发现 → `status=unavailable / no_gc_freeze_metadata_for_declared_candidate`；
  显式指向 A 的文件 → `rejected`，problems 恰为
  `schema_mismatch, freeze_calls_must_be_exactly_gc.collect_and_gc.freeze, gc_disable_forbidden,
  threshold_adjustment_forbidden, restore_not_confirmed, restore_calls_must_include_gc.unfreeze`。
  即：即使飞行本场正常，C1 也无法获得独立比较器结论，且 `complete` 无法成立。
- 修复要求（建议 A 侧执行，保留现有富报告）：
  1. 由 `ManagerGCFreeze` 产出一个合同投影（新 `contract()` 或并入 `report()`），字段严格按上表；
     `restore.calls` **只在真正调用过** `gc.unfreeze` 时包含它，`restore.restored` 只在确认
     freeze_count 归原后为 true（noop 路径不得冒充）。
  2. runner 在 run 目录根另存 `gc-freeze.json`（与 `manager-gc-candidate.json` 并存即可）。
  3. A 的测试补一条断言该合同（现有 23 项未覆盖它，因此全绿也不代表跨模块可验收）。
- 若裁定改由比较器适配 A 的 schema，则需同步改 `docs/plan/33-rate-measured-candidate-20260912.md`
  §6 与合同测试；两处不能各说一套。

## 4. OMP 独立结果现状（不可当作通过）

- 比较器合同测试独立复跑：`validation/test_compare_joint_gc_diagnostics.py` → **17 passed, 4 subtests
  passed**（与 plan §6 的"17 项全绿"一致）。
- `validation/coordination/gc-diagnostic-comparator-20260912/self-check-7bdfxkb.json`：
  `status=unavailable`，`reasons=["candidate:gc_freeze_contract:unavailable"]`——对原 7bdfxkb 只读自比，
  如实报告"无候选元数据"，**没有**冒充 candidate，也没有 `performance_pass`。这是正确的边界，但
  它**不是**对 A 候选的行为结果；当前不存在可采信的独立候选结论。

## 5. 控制场身份与完整运行命令（同身份单变量）

控制场实测（`validation/33-rate-profile/diagnostic-7bdfxkb/result.json` 只读）：
`joint-public-flight-7bdfxkb_`、epoch `85df8c49b8f64de8ba794cff149696d1`、
`full_xyz_pv_yaw_v1`、`async_model_evidence_requested=true`、无 planner release、
AP mixed `1e6250ef…`、Control c2IXOr `6fe8c0b3…`、message `29969da0…`、PX4 钉值 `d7e905b3…`、
38 个 source、`source_unchanged=true`、`cleanup_errors=[]`。

候选场只允许相对控制场多一个 `--manager-gc-freeze`（及因此新增的 candidate source）。完整命令：

```bash
cd /root/wksim-release-acceptance-fe3
WKSIM_JOINT_CPU_TIMING=1 WKSIM_JOINT_RATE_TIMING_PROBE=1 \
bash tools/run-joint-flight.sh \
  --task-profile full_xyz_pv_yaw_v1 \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
  --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
  --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
  --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219 \
  --async-model-evidence \
  --manager-gc-freeze
```

- 两段 PV 由 `full_xyz_pv_yaw_v1`；不带 `--px4-manifest/--px4-sha256`（PV 分支拒绝 alternate probe，
  `run_joint_flight.py:1097`），不带 `--planner-release-proof`、`--pause-probe`、`--dds-loss` 等。
- 运行前按 plan §4.2 只读复核四处 SHA；`--manager-gc-freeze` 已在 `run` 子 parser（`run --help` 实读）
  且 shell 透传（`run-joint-flight.sh:22`）。命令解析层已验；本报告不含实际执行。

## 6. 假说边界与可反驳指标（不承诺必过）

真实原件只支持"共现+嵌套"：`joint-wire.jsonl.gz` 中唯一 gen2 GC（`collected=0`、thread CPU
24.33 ms、tick 107572）完全嵌在同 tick 的 PX4 wait（24.79 ms）内，该 wait 又在 step 的
`native_inputs` 内；同场最大 entry lateness 20.75 ms 落在同一 tick。**没有对照、没有重复场**，
因此必要性/充分性均未证明；不得从单场推出"必然转绿"。

同身份重跑后逐项复核（可反驳，缺一不可）：
1. 计时窗内是否仍有 gen2 落在 `diagnostic_gc_timing`，其 `thread_cpu_ns` 最大值；
2. 同 tick `diagnostic_step_cpu_timing.native_inputs` 是否再现 ~25 ms 级 wall/cpu；
3. 最大单次 work-over / 最大 `entry_lateness_ns` 是否再现 ~20 ms 级；
4. 三项均无变化且最大 stall 无 GC 伴随 → **C1 被反驳**为主因。
另须报告 freeze 的一次性 `collect()` 成本与 `get_freeze_count()` 归 0 证据；probe 场不得作
rate/PV/Full 通过证据（`joint_profile.py:219-220`）。

## 7. 有边界的通过状态（仅限第 0 节 SHA）

- **通过**：设计边界与 runner 清理链四项全部满足；D1/D2 已修（逐行证据）；默认路径不变；纯测试
  `test_manager_gc_candidate.py` 独立复跑 **23 passed**；flag 解析与 PV/MIXED 限定已验；比较器
  17 项合同测试独立复跑通过。
- **未通过 / 未证**：D3 跨模块合同（现快照必然 `unavailable`/`rejected`）；OMP 对候选的独立行为
  结果（当前不存在）；实际诊断场（未运行，且属主会话执行范围）；24.33 ms 与 latch 的因果（未证）。
- **A 可直接接续**：修 D3（文件名+字段已给出，最小改动），补一条合同测试；随后由 OMP 以
  `--baseline …7bdfxkb_ --candidate <新场目录>` 重跑比较器，`gc_freeze_contract` 达到 `validated`
  且身份兼容通过，才算取得 C1 的可反驳对照结论。
