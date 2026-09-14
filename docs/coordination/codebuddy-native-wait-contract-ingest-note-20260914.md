# CodeBuddy native-wait 契约与输入计时文档的历史语境绑定（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时权威 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（写作时点的当前基线）。架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 只以 `git merge-base --is-ancestor` 祖先检查绑定（写作时点对 HEAD 退出码 0）——**本批次对 HEAD 一律用祖先检查，不做永久 HEAD 相等断言**；本批次提交后 HEAD 前进（含无关的已复核提交）不使本登记失效。配套离线测试：`validation/test_codebuddy_native_wait_contract_context.py`。

## 0. 本文件的地位

本文件只做一件事：把两份已 tracked 的 native-wait 契约/输入计时文档**按字节绑定**为历史语境（context-only，KEEP），并显式登记其中已被后续字节取代的历史性论断。它自身不构成任何验收、批准、收口或复核记录；被绑定文件同样不构成这些。本文件为纯只读复核产物：未修改被绑定文件或任何既有 tracked 文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未提交 Git、未触碰真实 index/refs、未 stage/commit/reset/clean/push；未联网；未重跑 #83。

**显式边界**：本批次是 context-only——不关闭任何 G6/Full 结论，不构成 #84 收口，不重跑 #83；既有固定门槛（fixed tick 四 tick 边界、group 四 tick 组、no-catch-up `previous_start+period_ns` 锚定、100ms `LATE_LIMIT_NS`、full-window 捕获窗、physics 物理步长不变量、identity `diagnostic_only` 分类）原样保留、不升格、不改写。

## 1. 历史语境绑定（字节级，写作 HEAD 现场重算，工作树 = HEAD 树）

| 被绑定文件 | SHA256 | bytes |
| --- | --- | --- |
| `docs/coordination/native-wait-integration-contract-20260913.md` | `947e759873513ce8d1f11363cb6df9c8c5fc7dc1c868037fbff3b24e90a7b823` | 6132 |
| `docs/coordination/claude-native-input-timing.md` | `f15cd0e28396722c23e005f38b2738ca2dfa889975f5f38ae345b7cbacaf0735` | 8714 |

两份均 tracked、工作树干净（`git status --porcelain` 对两路径为空）。裁决：**KEEP，作为历史语境**（context-only historical context）。

## 2. 源锚独立核验（对当前 tracked 字节重算）

| 源文件/证据 | SHA256 | bytes | 关键锚（本登记现场逐行核验成立） |
| --- | --- | --- | --- |
| `Simulator/wksim_runtime/joint_rate.py` | `0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4` | 7271 | `LATE_LIMIT_NS=100_000_000`（6 行）；no-catch-up `earliest=max(ideal,…,previous_start+period_ns)`（93 行）；两个最终 1ms 自旋分支 99-103（自旋 100-101）与 114-118（自旋 115-116）；释放沿窗口不变式注释 120-123；sleep 124；`actual_start_ns`/`previous_start` 126-127；`rate_group_start` 记录 128-130 |
| `Simulator/wksim_runtime/joint_rate_probe.py` | `a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653` | 7826 | 显式 env opt-in `timing_probe_enabled` 23-30；`timing_probe_identity`（`classification="diagnostic_only"`）33-39；probe 终值记录 222-224 |
| `Simulator/wksim_runtime/joint_profile.py` | `90cc868b8050b41e54ef0c38cf20104c58aefb97f07d1448dfd0be1f8633320a` | 31113 | 标记拒绝循环 274-275（当前三元标记表，见 §3）；必需集 330-334（当前含两个 pacer 文件，见 §3）；`required <= sources.keys()` 335；逐字节封存循环 337-339（`evidence_sha256['source__'+name]`） |
| `Simulator/wksim_core/joint.py` | `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50` | 15808 | 54 行 `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`（默认关的 opt-in 诊断门） |
| `validation/33-formal-promotion/current-mixed-oxv29042/result.json` | `68114715ac4057337fe8174cd708f03ae8343e205335ab61a63ca4ad47e73dbd` | 130322 | `status=failed`、`source_unchanged=True`；`source_sha256` **确实包含** `Simulator/wksim_runtime/joint_rate.py` 与 `Simulator/wksim_runtime/joint_rate_probe.py`，且两者值与当前工作树字节逐位一致（`0b53a16a…` / `a8bac9ac…`）——该次运行的 pacer 源码已被自带证据绑定 |

契约 §5 对该 result.json 的描述（pacer 源码被绑定、result 本身 status=failed、正式通过件以 profile 证据钉为准）经现场重读成立。契约对 joint_rate.py 的行号锚（6、93、99-103、114-118、120-123、124、126-127、128-130）与对 joint_rate_probe.py 的行号锚（23-30、33-39、222-224）均对当前字节成立。

## 3. 契约 §5 历史漂移的显式登记（older exclusion/two-marker claim 是历史的，不是当前的）

- **契约所记（2026-09-13 写作时点，历史性）**：§5 称 "joint_profile.py:328-331 的必需集不含这两个文件"（即不强制 pacer 源码进入必需集），且 §5 第 4 点把启用方式仅负向绑定到单标记 `rate_timing_probe` 拒绝（旧两标记表 `rate_timing_probe`+`group_work_timing` 时代的表述）。
- **当前字节（本登记现场核验）**：`joint_profile.py` 必需集已移至 330-334 行并**同时包含** `Simulator/wksim_runtime/joint_rate.py`（333 行）与 `Simulator/wksim_runtime/joint_rate_probe.py`（334 行）；标记拒绝表（274 行）已是三元 `('rate_timing_probe', 'group_work_timing', 'perf_switch_capture')`，**包含 `perf_switch_capture`**。契约 §6.1 所请（把 pacer 文件加入必需集）在当前字节中已发生。
- **结论**：旧的"必需集排除 pacer 文件 / 两标记表"论断是**历史性记录**，不描述当前 `joint_profile.py` 字节；未来任何引用必须以当前字节为准。本登记不改写契约原文（其字节被 §1 绑定），只登记漂移。

## 4. 外部 /root probe 证据：不可复现，PASS 永不依赖

`claude-native-input-timing.md` 引用 `/root/wksim-scheduler-probe-35728b1-03`（probe-03）中 tick5504（5.754904ms）与 tick2000（5.130931ms）等外部捕获证据。该证据位于外部环境、本 checkout 不可复现、本批次也未运行任何真实捕获；本登记与其配套测试只把它当作**文档内的字节级文字锚**核对（证明文档说了什么），**绝不作为任何 PASS 的依赖**——所有 PASS 断言只依赖 tracked 字节、哈希与行锚。

## 5. 排除项

- **tracked 活合同** `docs/coordination/perf-stream-contract-20260913.md`：实时 perf-stream 合同是**活指针**，在本批次候选之外；本登记只引用其存在与 tracked 状态，不绑定其字节、不取代它。
- **untracked 文档** `docs/coordination/claude-native-wait-next-probe.md`：写作时点 `git ls-files --error-unmatch` 报 pathspec 未匹配（untracked）；本批次不绑定其字节、不将其纳入候选、不为其任何内容背书。若其后续被独立复核并 tracked，属后续批次的演进，不影响本登记。

## 6. 不声称清单（显式）

- 未把历史语境升格为当前执行、验收、批准或收口；不关闭任何 G6/Full 结论；不构成 #84 收口；不重跑 #83；不触发/建议/替代任何工单重跑；
- 未修改被绑定文件或任何 tracked 文件；未触碰真实 Git index/refs；未 stage/commit/reset/clean/push；未联网；
- 未运行任何 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行程序；§4 外部证据未被运行、未被复现、也未被采信为 PASS 依据；
- §2 行号锚只对当前 tracked 字节有效；这些字节今后变化时，本登记对旧字节的绑定继续有效，对当前字节的适用性须重新核验（与契约 §6.6 对旧证据的逻辑一致：旧证据只对旧字节有效）。
