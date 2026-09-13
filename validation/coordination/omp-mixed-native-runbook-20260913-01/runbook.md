# 真实 MIXED perf 诊断运行：精确执行手册（main 独占 native）

- 类别：new-development 诊断执行手册 + 只读预检器；**本包自身未运行** native/ROS/飞控/模型/UE/MATLAB，未启动或终止任何进程。
- 写入边界：仅 `validation/coordination/omp-mixed-native-runbook-20260913-01/`；未改任何既有文件；未 `git add/commit/push`。
- 机器可读副本：`runbook.json`（schema `wksim.omp_mixed_native_runbook.v1`）；只读预检器：`verify_runbook.py`。
- **本场永不得登记为正式证据**：runner marker `perf_switch_capture` 自带 `classification='diagnostic_only'`、`formal_evidence=False`；正式门 `Simulator/wksim_runtime/joint_profile.py:274-276` 以**键存在**拒绝该 marker（33c2b06 已落地，与 `rate_timing_probe`/`group_work_timing` 同列）。instrumented 场可被原始审计复核，但永远不是正式 MIXED/PV/#84/G6/Full 证据。

## 0. 开工核验（本包已做；main 执行前必须重核）

已做（本 Windows 生产者，只读）：

| 项 | 结果 |
| --- | --- |
| cwd / 分支 | `C:/Users/PC/Documents/odid编译/wksim`，`main` |
| HEAD（派发时 / 交付时） | `0a1caa116e31…` / `13096b508973…`（期间并发推进 `287f8ec`、`72ef95d`，均为仅证据提交；`git diff 0a1caa1..13096b5 -- tools/ Simulator/` 为空，全部钉值按文件 SHA 而非提交号生效） |
| 架构祖先 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 |
| perf 接线提交 | `100ef1aafcc19c006d93eeb16b0c41e2352cdee6` 是当前 HEAD 祖先，**但不是候选同步点 `386f713` 的祖先** |
| 被引用文件 SHA | 全部本地实算，见 §10 与 `runbook.json.source_sha256`；与最近 OMP/Codebuddy 审查记录逐字一致 |

main 执行前重核（候选检出上）：`git -C /root/wksim-architecture-acceptance-20260913 rev-parse HEAD`、`status --porcelain` 必须为空、`merge-base --is-ancestor f333316… HEAD` exit 0、`merge-base --is-ancestor 100ef1a… HEAD` exit 0。

## 1. 冻结身份（逐项带来源；旧身份只作历史对照）

| 角色 | 路径 | SHA256 | 来源 |
| --- | --- | --- | --- |
| AP mixed manifest | `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json` | `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c` | `joint-profiles.json` mixed 行 + `ap_mixed_candidate.FINAL_AP_SHA` |
| Control（当前冻结） | `/root/wksim-joint-control-c2IXOr/build.json` | `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e` | `FINAL_CONTROL_SHA`；`short-cycle-goal.md` |
| Message | `/root/wksim-ros2-Rzj3Pf/message-build.json` | `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219` | `FINAL_MESSAGE_SHA`；MIXED task + 当前 Control 时**必需**（`ap_mixed_candidate.py:112-116`，缺失即拒绝） |
| PX4（profile 钉值） | `/root/wksim-px4-state-ONa1Kw/wksim-build.json` | `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6`（二进制 `93b4ebe0…8d10602a`） | 目录钉值；**不进 CLI**（MIXED 分支视 `--px4-manifest` 为 alternate probe 直接拒绝）；由准入基线链核验；本场**不会产生** `live/px4-build.json` |
| 模型库 | `/root/wksim-private-tmp-cxrbwjyr/artifacts/wksim-model-ms14otyn/libwksim_model.so` | 无独立预钉（见 §9 缺口 G3） | `joint-profiles.json` `joint_quad_dds_v1.model_library`；`admit()` 原样返回，runner 在运行时核验原准入链 |
| perf 库（钉定） | `/root/wksim-perf-python-admission-apup9qju/libwksim_perf_stream.so` | `37d9651282bce0da059828056796683b94e780461f7918e60c3e1e77e2130020` | 构建收据 `perf-python-native-admission-20260913-01/build-receipt.json`（源 `aa807f3b…`/`ef1eabf2…`，`cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -shared -fPIC`，导出 `wksim_perf_start/stop/last_error`） |

不得使用的旧 Control 身份：`0DQQz9`（`25edbf81…`，正式目录行仍钉它，但本诊断走 CLI 覆盖）、`rWolCy`（`a6a17b42…`）、`ZlTVa4`（`3d04d53a…`）、`OEvS3W`（`d9fdfc74…`）。

## 2. 前置 A：候选检出同步（硬前置，当前不满足）

候选 `/root/wksim-architecture-acceptance-20260913`（分支 `codex/architecture-acceptance-20260913`）最后核验于 `386f713a7752…`（见 `architecture-candidate-sync-20260913-02/receipt.json` 与库构建收据）。**`386f713` 不含 runner perf 接线 `100ef1a`**（`merge-base --is-ancestor 100ef1a 386f713` → exit 1）。不同步则候选 runner 没有 `--perf-library/--perf-library-sha256`，parser 直接 exit 2。

按既有机制快进（`architecture-candidate-sync-20260913-02/sync.py` 的方法：bundle → `git fetch <bundle> refs/heads/main:refs/remotes/main-coordinator/main` → `git merge --ff-only`），目标提交必须含 `100ef1a` 且下列文件逐字节等于 §10 钉值：`tools/run_joint_flight.py` `167a3c07…`、`tools/run-joint-flight.sh` `ea012da6…`、`Simulator/wksim_runtime/perf_capture.py` `c196616f…`、`joint_rate.py` `0b53a16a…`、`joint_profile.py` `90cc868b…`、recorder C/H、consumer `dee9a3b5…`。同步后重记候选 HEAD 与祖先检查到本场收据。**不迁移任何私有接线；不整目录覆盖。**

## 3. 前置 B：两 WSL 发行版进程扫描 + boot_id + 60 秒新鲜度

逐字复用已执行协议（`three-deepseek-main-acceptance-20260913-01/precheck.py`，脚本全文在 `runbook.json.precheck.script`）。从 Windows 主机对每个发行版执行：

```text
wsl.exe -d Ubuntu-22.04  -u root -- python3 -   < precheck 脚本 → precheck-Ubuntu-22.04.json
wsl.exe -d RflySim-20.04 -u root -- python3 -   < precheck 脚本 → precheck-RflySim-20.04.json
```

- 两发行版 `found` 都必须为 `[]`（markers 24 项，含 arducopter/px4/microxrceagent/prometheus_control/run_joint_flight.py/wksim_core.worker/matlab/unrealeditor 等；comm 为 bash/sh/dash/timeout 的跳过）。
- 启动器启动时复核（manager99 `launch.sh:11-14` 同形）：重读 Ubuntu-22.04 的 `/proc/sys/kernel/random/boot_id`，要求两份 precheck 的 `boot_id` 与之相同且 `-1 <= time.time()-checked_unix <= 60`；任一不满足即**重新扫描**，不得用过期扫描启动。
- 最近一次已执行样例：`perf-overhead-long-20260913-01/prechecks.json`（两发行版同 boot `d01554f1…`、`found=[]`）。

## 4. 前置 C：清单与库字节复核（任一不符即不启动）

```bash
sha256sum /root/wksim-ap-mixed-fhuf05l9/mixed-build.json      # 期望 1e6250ef…cc6ce94c
sha256sum /root/wksim-joint-control-c2IXOr/build.json         # 期望 6fe8c0b3…16cf5e7e
sha256sum /root/wksim-ros2-Rzj3Pf/message-build.json          # 期望 29969da0…d27a96219
sha256sum /root/wksim-px4-state-ONa1Kw/wksim-build.json       # 期望 d7e905b3…3d4cb6（只读复核，不进 CLI）
sha256sum /root/wksim-perf-python-admission-apup9qju/libwksim_perf_stream.so  # 期望 37d96512…2130020
```

`.so` 位于 `/root`（在 runner 的私有 `/tmp` overlay 之外，运行期可见）；launcher 在加载期间保持其字节稳定，runner 在 finalize 时重算摘要（`run_joint_flight.py:130-131`），不符即 fail-closed。

## 5. 主命令（完整 argv）

环境（manager99 launch 同形净室）：`export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`，`export PYTHONDONTWRITEBYTECODE=1`，并 `unset CMAKE_PREFIX_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH ROS_DISTRO PKG_CONFIG_PATH WKSIM_JOINT_CPU_TIMING WKSIM_JOINT_RATE_TIMING_PROBE`。**两个计时探针必须不存在于环境**：它们是另一种会改写被测路径的诊断；当前 runner 未实现与 perf 的互斥（`100ef1a` 未落地审计建议 C1.5），故此处以操作边界强制执行。

```bash
cd /root/wksim-architecture-acceptance-20260913
timeout --signal=TERM --kill-after=120 1500 \
  bash tools/run-joint-flight.sh \
  --task-profile xy_velocity_z_position_yaw_v1 \
  --async-model-evidence \
  --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
  --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
  --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
  --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
  --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
  --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219 \
  --perf-library /root/wksim-perf-python-admission-apup9qju/libwksim_perf_stream.so \
  --perf-library-sha256 37d9651282bce0da059828056796683b94e780461f7918e60c3e1e77e2130020 \
  2>&1 | tee <run-receipt-dir>/run.stdout.log
```

- 包装器语义：`unshare --net --ipc --mount --propagation private` 后 `exec python3 -B <repo>/tools/run_joint_flight.py run <argv>`，并 source 冻结的 ROS/DDS setup（`tools/run-joint-flight.sh` 全文）。
- `--async-model-evidence` 沿用该诊断族的现行 main 裁定（`33-rate-next-diagnostic-20260912.md` §4.3；xtj8wk8i/nqyqcagl 同配置）；parser 两种形态都接受，本手册固定为含该 flag 的唯一规范 argv。
- **禁止 flag**（MIXED 分支逐字拒绝或本 runner 不存在）：`--px4-manifest/--px4-sha256`、`--ap-manifest/--ap-sha256`、`--ap-pv-manifest/--ap-pv-sha256`、`--pause-probe`、`--repeat-paused-clock`、`--scene-lifecycle`、`--scene-lease-loss`、`--dds-loss`、`--native-state-trace`、`--probe-land-freshness`、`--model-promotion-flight`；`--manager-gc-freeze`/`--early-work-timing`/`--owned-scheduling-snapshot` 只存在于已回退的私有 runner，本 runner 没有。
- 内部边界不变：`WALL_LIMIT=900` 墙秒、`MAX_TICKS=180000`、候选传输初始化 15 秒。

### 超时只清理自有 PGID

`timeout` 不带 `--foreground` 时把包装链放进**自己新建的进程组**并只向该组发信号：TERM → runner 的 `SIGTERM→InterruptedError`（`run_joint_flight.py:440-442`）→ 外层 `finally` 先 `finalize_perf_capture`（:1100-1101）再 `cleanup_children`（:1102）。飞行子进程全部由 `start_new_session=True` 启动（各自 PGID==各自 PID），**不在** timeout 组内，由 runner 自己的 `stop_children` 按 `killpg(child.pid, SIGTERM)→wait 5s→killpg(child.pid, SIGKILL)→wait 5s`（`runtime.py:100-123`）收口。`--kill-after=120` 的 KILL 仍只到同一个自有 PGID。若 runner 在 KILL 后仍不退出：只能按 `live/children-start.json` 逐个子进程**重核 pid+pgid+start_ticks 身份**后对其自有 PGID 发信号，随后重跑 §3 的两发行版扫描；**绝不**扫描或信号任何其它进程。

## 6. runner 生命周期与不变量（逐行锚点，均不改动）

- marker：`result['perf_switch_capture']` 建于 :468-477（外层 `try` 之前），`strict_consumer` 钉死 consumer 源路径+SHA、`require_kernel_counter=True`、输出名 `perf-decoded.json`。
- 构造 :863-866（rate 创建后、首个子进程前）：构造器 fail-fast 校验内核 `6.6.87.2-microsoft-standard-WSL2`、绝对已存在 `.so`、精确小写 SHA、输出路径不存在（`perf_capture.py:26-63`）。
- start :961-962（`physics.connect()` 后、主循环前）；owner pid+native tid 记录，每次操作复核（`perf_capture.py:78-80`）。
- 窗口：`mixed_rate_segment_<segment_id>`，`start_ns=rate.last_summary['anchor']['wall_ns']`，`end_ns=rate.last_end`；必须落在捕获 inner span `[enable_after_ns, disable_before_ns]` 内；finalize 重读 host `boot_id` 与 meta 比对（:106-137）。
- stop/密封：外层 `finally`（:1099-1101）先于 `cleanup_children`；任何捕获/窗口/密封/库身份失败 → `result.status='failed'`，fail-closed。
- 速率不变量：1ms tick（`SceneClock.STEP_NS=1_000_000`）、4 tick 组（`MACRO_TICKS=4`）、0.5×（组周期 8ms）、无追赶（`begin_group` earliest=`max(ideal, previous_start+period_ns)`，`joint_rate.py:89-93`）、100ms 晚限（`LATE_LIMIT_NS=100_000_000`）、完整单段窗口（10s/60s 滑窗 2%/1% 预算照旧）。本运行一行不改这些。
- 产物：archive=`validation/joint-public-flight-<新>`、live=`/root/wksim-joint-flight-<新>`（均 fresh mkdtemp）；`perf-switch.raw`、`perf-switch.meta.json`、`perf-windows.json` 随 `copytree` 入 archive；5 份 perf 源进 `source_sha256`/`source__*.txt`。

## 7. 赛后：strict consumer（完整命令）

runner 只"为外部 consumer 密封"，从不自跑 consumer（`strict_consumer_passed` 恒 False）。runner 退出后由 main 在 archive 上执行：

```bash
cd /root/wksim-architecture-acceptance-20260913
python3 -B validation/coordination/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py \
  --raw     <ARCHIVE>/perf-switch.raw \
  --metadata <ARCHIVE>/perf-switch.meta.json \
  --windows  <ARCHIVE>/perf-windows.json \
  --require-kernel-counter \
  --output   <ARCHIVE>/perf-decoded.json
```

- `--output` 必须不存在（`x` 独占创建；已存在 → exit 3 `output_exists_refusing_overwrite`，**换名，绝不删证据**）。
- 绑定校验：报告 `inputs.raw_sha256/metadata_sha256/windows_sha256` 必须与 `result.json` 的 `perf_switch_capture.outputs` 三项 SHA 逐字相等；不等 = archive 被替换，fail-closed。
- 顺序：**先 consumer，后** `tools/audit_mixed_control.py <ARCHIVE>`（审计的 `evidence_sha256` 封存目录全文件，使 `perf-decoded.json` 被一并封存）。绝不把解码结果回填 `result.json`。

预期产物（exit 0）：stdout 单行 `{"ok":true,"output":…,"pairs":N,"records":M,"windows":1,"raw_sha256":…,"metadata_sha256":…}`；`perf-decoded.json` 含 `schema=wksim.perf_switch_consumer.v1`、`classification=diagnostic_only`、`full_acceptance=false`、`flight_conclusion=null`、`stream_completeness_proven=true`、`window_completeness.kernel_lost_count=0`、窗口 `mixed_rate_segment_<id>` 的整数纳秒交集。

### consumer 失败分类（exit 3，stderr `{ok:false,reason,detail}`，不写输出）

| reason 族 | 含义与处置 |
| --- | --- |
| `kernel_loss_counter_required`/`_unavailable`/`_read_invalid`/`_value_invalid` | 完整性依赖的调用缺/坏计数器；该捕获只能作 inspection-only，窗口未被证明 |
| `kernel_loss_counter_nonzero` | 内核报告丢事件；捕获作废，保留全部字节 |
| `windows_outside_capture_bounds` | 窗口越出 inner span；runner 窗口导出或捕获跨度问题，本场窗口测量不成立 |
| metadata schema/config/lifecycle/collector 系列、raw 长度≠`captured_bytes`、LOST/未知/截断记录、非交替/未配对、时间戳越界、异主身份 | 捕获合同拒绝；保留原件，不重跑覆盖 |
| exit 4 | IO 错误；修路径，不动证据 |

## 8. 整场失败分类（含 runner 侧）

| 分类 | 触发 | 结果 |
| --- | --- | --- |
| `precondition_failed` | §3/§4/候选同步任一不符 | **不启动**；无场次产生 |
| `admission_failed` | `mixed_admission.ok=false` | 子进程创建前失败；未测量 |
| `capture_construct_failed` / `capture_start_failed` | 构造器/start 抛错 | fail-closed；未测量 |
| `latched_no_window` | `RateUnmet` 在 `close_segment('completed')` 前 latch：`last_summary` 为空，finalize 报 `lacks a completed MIXED rate segment` | raw/meta 存在、无 `perf-windows.json`；consumer 无 `--windows` 只能 inspection-only；**完整窗口测量未发生**；latch 是合法诊断结果，不是回归 |
| `sealed` | marker `sealed_for_external_consumer` | 执行 §7 |
| `timeout_path` | 见 §5 超时段 | runner 优雅收口优先；KILL 只到自有 PGID |

赛后必做：重跑两发行版扫描（`found=[]`、boot 不变），并确认 `result.json` 每个 child 的 `remaining_group_members` 为空。

## 9. 缺口与最近可复用收据（不猜，精确报告）

- **G1（硬前置）**：候选检出最后核验于 `386f713`，不含 `100ef1a`；必须先按 §2 快进并逐字节核对。最近收据：`architecture-candidate-sync-20260913-02/receipt.json`、`perf-python-native-admission-20260913-01/build-receipt.json`（确认检出路径/分支/内核）。
- **G2**：当前 boot_id、候选工作树干净度、清单与 `.so` 的在盘字节无法由本 Windows 生产者在不启动 WSL 进程的前提下观测；全部列为运行时门（§3/§4），不作假设。最近收据：`perf-overhead-long-20260913-01/prechecks.json`、`perf-python-native-admission-20260913-01/run-receipt.json`。
- **G3**：模型库 `…/libwksim_model.so` 无独立字节钉值（`short-cycle-goal.md` 只引 `e59ab914…` 链前缀）；与既往 MIXED 家族场次一样依赖 runner 自身的准入链核验。最近收据：`2026-09-13-final-combo-pv-pass.md`（1w6dru32 archive 内 `model-build.json`）、`validation/33-rate-profile/early-work-xtj8wk8i/bundle-manifest.json`。
- **G4**：候选在 `386f713` 时只逐字节核验过 10 份选定源码；快进后必须按 §2 的全表重核。最近收据：同 G1。

## 10. 稳定 SHA（本包引用的 repo 文件，本地实算）

| 文件 | SHA256 |
| --- | --- |
| `tools/run_joint_flight.py` | `167a3c0790dde0bbef3b7bd2fee24616bdc623852aa7478a4c9356f425a670bf` |
| `tools/run-joint-flight.sh` | `ea012da68bd8fcb3e25383197bf5a9f076aecfe5d3fd9a966675aa0d69fdc883` |
| `tools/ap_mixed_candidate.py` | `5420e1443d58c66eca379b29d8bdb15ea044335dd343cca2d9da88d2364e368f` |
| `tools/mixed_control_task.py` | `76adbd47fbe70c4fda4deabd893cc368b9fbd0ceeaabe4a6b7a59e597ed358fc` |
| `tools/joint_control_candidate.py` | `4e34bbfa8ff8bae874e29673a58df4f48445a2c325c5165cdf352b80f2c89131` |
| `tools/joint_message_candidate.py` | `5babcdca4601a40befc804ed3e34d6dc9e8c0a05b827db43374dbc3dd90a9efe` |
| `Simulator/wksim_runtime/perf_capture.py` | `c196616fe8324eed2d8b294ef52aaec1f982eb5330abbeb7ee17094399f32e0f` |
| `Simulator/wksim_runtime/evidence.py` | `4f7f2e601ce3c2edfe54c1c48ed35d41133304c2b1fa56a969148c6ccbbfcb7a` |
| `Simulator/wksim_runtime/joint_rate.py` | `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4` |
| `Simulator/wksim_runtime/joint_profile.py` | `90cc868b8050b41e54ef0c38cf20104c58aefb97f07d1448dfd0be1f8633320a` |
| `Simulator/wksim_runtime/joint-profiles.json` | `190582638d124814f7d10818925d0f0431eb8f2aa4366a5192a4ff653cb2f88a` |
| `Simulator/wksim_runtime/runtime.py` | `11b9b326ff9972b999f3d22ecb053329afc9f443f623826d934b2c7154c136d2` |
| `Simulator/wksim_runtime/examples/joint-mixed.json` | `f344fb3049cafd3a5b67df30eed71c2171d156babaaeddbd63349f94a92108cf` |
| `…/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c` | `aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2` |
| `…/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h` | `ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823` |
| `…/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py` | `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc` |
| `validation/test_run_joint_perf_capture.py` | `05ddf8638e804a87a1f4b32912c62237332e5ca16e63b39d420b26fe379d7ce0` |
| `validation/test_perf_capture.py` | `f4d95ae49478729e2f4c3a508f9ef452d3f6b5acffd0c8a3301bc72155d4f3c3` |

引用审查基线：OMP runner 审查（`omp-mixed-perf-runner-review-20260913-01`，无 P0/P1，4 项 P2 均为非阻断）、Codebuddy 准入链审查（`codebuddy-perf-admission-review-20260913-01`，阻断 0、非阻断 5）、Codebuddy 核心原生加载审查（`codebuddy-core-native-audit-review-20260913-01`，3 项 P1 针对**审计工具**的判定精度，不影响 runner/适配器字节本身）、接线审计（`ds-perf-mixed-hook-audit-20260913-01`）。

## 11. 停止声明

本目录在 `.gitattributes`、`runbook.md`、`runbook.json`、`verify_runbook.py`、`test-output.txt`、`SHA256SUMS` 写完后**停止写入**。未修改任何既有文件；未 `git add/commit/push`；未执行 native/ROS/飞控/模型/UE/MATLAB；未启动或终止任何进程。本手册的运行步骤全部留给 main 独占执行。
