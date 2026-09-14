# CodeBuddy gc-freeze-review-20260912 历史语境绑定与 D3 折叠登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时的历史基线 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（writing-time historical baseline；绑定不要求当前 HEAD 与其逐字节相等，只要求其作为当前 HEAD 祖先持续成立，见 §9）；架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 经 `git merge-base --is-ancestor` 验证为写作时 HEAD 祖先（exit 0），修订后与 `31e5b65f` 同为当前 HEAD 的 fail-closed 祖先要求。

## 0. 本文件的地位

本文件只做三件事：把 `docs/coordination/codebuddy-gc-freeze-review-20260912.md`（C1 `--manager-gc-freeze` 独立复核）**按字节绑定**为历史语境，登记其核心未决发现 D3 在当前 tracked 权威中的折叠状态与 23/23 记录的效力边界，并在 §9 登记伴生测试候选生命周期判定（A/B/C）的字节级修订（不新增任何权威）。它自身不构成任何验收、批准、收口或复核记录；被绑定文件同样不构成这些。本文件为纯只读复核产物：未修改被绑定文件或任何既有文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未提交 Git；未联网；未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`、`rolling-six-plan-20260912.md`、`claude-native-wait-next-probe.md`、`validation/_probe_delivery_contract.py`）。

## 1. 历史语境绑定（字节级，写作 HEAD 现场重算）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/codebuddy-gc-freeze-review-20260912.md` |
| SHA256 / 大小 | `64d0e8766274df1ac8cd8d136ec9300b080bc755e0a1694a1272aae3ad406546` / 10594 bytes |
| 性质 | CodeBuddy 对 C1 候选（A 交付）的独立复核快照（2026-09-12），只读、historical context only、非权威 |

## 2. 源快照 SHA256/bytes 重算（2026-09-14 于 HEAD `31e5b65f` 现场复算）

被绑定文件 §0 钉住的三份源快照，与 tracked `validation/coordination/c1-delivery-20260912/` 交付快照及 `delivery.json.source_sha256` **逐字节一致**：

| 文件 | 钉住/快照 SHA256 | 快照 bytes | 当前 HEAD 状态 |
| --- | --- | --- | --- |
| `tools/manager_gc_candidate.py` | `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66` | 11254（`c1-delivery-20260912/source__tools__manager_gc_candidate.py.txt`） | **HEAD 不存在该路径**；仅 tracked 快照保留 |
| `validation/test_manager_gc_candidate.py` | `637c403c3fe5ea44d097fb89479b10d353d51b2684c4fb52cdcf5d017a6aa6ad` | 15726（`c1-delivery-20260912/source__validation__test_manager_gc_candidate.py.txt`） | **HEAD 不存在该路径**；仅 tracked 快照保留 |
| `tools/run_joint_flight.py` | `fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246` | 78247（`c1-delivery-20260912/source__tools__run_joint_flight.py.txt`） | **已漂移**：HEAD 现算 `c8577093a62e4993c8048a69f4501984b3ee9045b8a73d26fb83aedc73acbb3b` / 79221 bytes |

即：被绑定文件的行号锚（§1/§2）以 `fd0b7ee6` 快照为准；对 HEAD 现树不适用。

## 3. 23/23 记录的效力边界（显式）

被绑定文件 §7 记录 `test_manager_gc_candidate.py` 独立复跑 **23 passed**；tracked `validation/coordination/c1-delivery-20260912/delivery.json` 同步载明 `"delegated_validation": {"manager_gc_candidate": "23 passed"}`、`"classification": "candidate_source_delivery_not_flight"`、`"native_started": false`。

该 23/23 **只是对 §2 钉住的历史 SHA 快照（`637c403c` / `cbf7b018` / `fd0b7ee6`）的一次独立复跑记录**，并且：

- **不是当前执行**：HEAD 上这两个测试/源路径已不存在、runner 已漂移（见 §2），当前树上不存在可复现该 23/23 的执行对象；
- **不是批准**：不构成对 C1 候选、对任何工单的验收或批准；
- **不是 #83 证据**：与 #83 的验收链无关，不得被引用为其证据；
- **不是收口**：不关闭任何缺陷、票据或决策项。

## 4. 锚复核结果（2026-09-14 现场核对）

| 锚（被绑定文件所引） | 状态 |
| --- | --- |
| `docs/plan/33-rate-measured-candidate-20260912.md`（§3/§6） | tracked；§3 钉住 `cbf7b018`/`fd0b7ee6` 与本文件 §2 一致；§6 现行合同见 §5（已修订，不再要求 `gc-freeze.json`） |
| `tools/compare_joint_gc_diagnostics.py:35,73,251-278` | 文件 tracked；行号属 **08e35350 提交前工作态**。HEAD 现算：`resolve_inputs` 在 `:333`，全文 **0 处** `gc-freeze.json`/`freeze_calls` 合同——行号与"要求 gc-freeze.json"的语义均不适用于 HEAD |
| `validation/test_compare_joint_gc_diagnostics.py` | tracked，存在；被绑定文件 §4 的"17 passed"为历史记录，本登记未重跑 |
| `validation/coordination/gc-diagnostic-comparator-20260912/self-check-7bdfxkb.json` | **磁盘存在但 untracked**（SHA256 `fb698d67faf5f10d8ad416e571531b5ca99a5990648890bb4faf0799f9c4f0a7`）；现场读得 `status=unavailable`、`reasons=["candidate:gc_freeze_contract:unavailable"]`，与被绑定文件 §4 引文逐字一致 |
| `validation/33-rate-profile/diagnostic-7bdfxkb/result.json` | tracked；现场核得 `run_id=joint-public-flight-7bdfxkb_`、`scene_epoch=85df8c49b8f64de8ba794cff149696d1`、`source_unchanged=true`、`cleanup_errors=[]`、38 个 source——与被绑定文件 §5 控制场身份一致 |
| `tools/run-joint-flight.sh:22` | tracked；`:22` 为 `exec python3 -B .../run_joint_flight.py run "$@"` 透传行，成立 |
| runner 行号锚（`fd0b7ee6` 快照）`:466/:791/:888-905/:1041/:1043/:1048/:1049-1050/:1062-1073/:1071` | 对 tracked 快照逐行核验**全部成立**（tick-0 校验、`:466` try、`:791` ExitStack、`:1048` finally→`:1050` cleanup_children、`:1071` 写 `manager-gc-candidate.json`、`:1061-1073` finally 内 restore） |
| runner 行号锚（`fd0b7ee6` 快照）`:906-907` prepare / `:908` physics.connect | **行号失准**：同一快照内 `manager_gc.prepare(...)` 实在 `:910`、`physics.connect()` 实在 `:911`（prepare 在 connect 之前、tick-0 校验在前的次序主张成立） |
| runner 行号锚 `:1097`（PV 拒绝 alternate probe） | **行号失准**：快照 `:1195` 才是 `parser.error('P+V requires exactly one explicit PV or mixed AP manifest/SHA pair and no alternate probes')`，`:1187` 为 `--manager-gc-freeze` 的 PV/MIXED 限定。内容主张本身经 `:1187/:1195` 证实成立 |
| `Simulator/wksim_runtime/joint_profile.py:219-220`（probe 场不得作正式证据） | **HEAD 行号失准**：HEAD `:219-220` 为空行；现算拒绝点在 `:274-276`（`for marker in ('rate_timing_probe',...)` → `raise ValueError('Formal mixed/PV evidence cannot include '+marker)`）。tracked `docs/plan/33-rate-measured-candidate-20260912.md` §5 同引该行号，属同一历史行号缝 |
| manager 候选行号锚（`cbf7b018` 快照）`:151-183/:196/:200-205/:223-228/:248-273` | 对 tracked 快照逐行核验**全部成立**（`_revalidate`、freeze 后立即 `_we_froze=True`、restore noop 路径、`def report`） |

## 5. D3 折叠：被 tracked 权威取代（非"已修复"）

被绑定文件 §3 的 D3 主张："A 产物无法通过 OMP 比较器**已声明合同**（要求候选目录存在 `gc-freeze.json`，schema `wksim.joint-gc-freeze.v1` 等）"。该主张对 2026-09-12 的比较器工作态成立；其**前提合同已被 tracked 权威取代**，当前树上 D3 按原样不再适用：

1. tracked `docs/plan/33-rate-measured-candidate-20260912.md` §3/§6（随 `08e35350` 入库，2026-09-14）已把候选合同改为**直接消费真实产物**：`result['manager_gc_candidate']` 与旁文件 `manager-gc-candidate.json`（两处都有须一致），并明文载明"比较器**不**要求主会话手造 `gc-freeze.json`，也**不**转换证明或改 runner 迁就自己"。同文件 tracked"当前结论（2026-09-14）"另载明：**#83 不重跑**（公共 PV `1w6dru32` 已通过并 CLOSED，本文 C1 仍是假说，不得触发/建议/替代 #83 重跑）、MIXED/G6/Full 未通过、下一 native 场仅主会话执行、本模块只维护离线比较器与纯测试。
2. tracked `tools/compare_joint_gc_diagnostics.py`（HEAD `31e5b65f`）全文无 `gc-freeze.json`/`freeze_calls` 合同；`resolve_inputs` 在 `:333`，按现行合同核验 `manager_gc_candidate` 报告字段（`original`/`prepare_check`/`freeze_count_after`/`restored_to_original`/`activation.clock_tick==0`/`events`/`source_sha256` 一致等）。
3. 后续 tracked C1 决策记录（均 tracked，仅按 tracked 内容描述）：
   - `docs/coordination/omp-c1-measurement-check-20260912.md`（OMP 对 C1 测量 v1 的五项意见）；
   - `docs/coordination/ds-c1-actual-analysis-20260912.md`（v3）与 `ds-c1-actual-analysis-20260912.json`：真实 C1 场 `ztdsk269`（带探针）/`vwen35gc`（无探针）对基线 `7bdfxkb_` 的实测分析——三场同为 `RateUnmet('rate_unmet/resource_insufficient')`；两 C1 场稳态方向相反（−13.3% / +12.9%）、**稳态 C1 效应不可复现**；早期窗损失在两个 flag-on 场出现而基线没有（提示性非结论性）；不建议放宽任何门限；
   - tracked 场证据 `validation/33-rate-profile/diagnostic-c1-ztdsk269/`（含 `manager-gc-candidate.json`，其 `source_sha256` 与本文件 §2 钉住值一致、`performance_pass=false`、`restored=true`）与 `validation/33-rate-profile/diagnostic-triple-20260912/`；
   - tracked `validation/coordination/c1-delivery-20260912/`（`delivery.json` + 六份源快照，分类 `candidate_source_delivery_not_flight`、`native_started=false`）。

**折叠语义**：与既有 ingest note 一致——折叠只表示 D3 所指的合同前提已被 tracked 锚取代，**不**表示 D3 的工程关切（跨模块合同可验收性）被任何一方"通过"；比较器现行合同下 `performance_pass` 恒不输出，C1 是否有效的可反驳对照结论仍以 tracked `ds-c1-actual-analysis` 的边界为准（未取得）。

## 6. 历史失败记录保全（不得随折叠丢失）

- 被绑定文件 §3：D3 在其快照时刻**未修**（文件名不符 + 报告缺合同字段）——原样保留于被绑定文件；
- 被绑定文件 §4：比较器对 7bdfxkb 自检 `status=unavailable`、`candidate:gc_freeze_contract:unavailable`——"无候选元数据，不冒充 candidate"的正确 fail-closed 行为；
- 被绑定文件 §7："未通过 / 未证"清单（D3 跨模块合同、OMP 独立行为结果、实际诊断场、24.33 ms 因果）——原样保留；
- tracked C1 实跑结局：三场 `RateUnmet`、稳态不可复现（`ds-c1-actual-analysis-20260912.md` §3/§5/§7）；
- tracked `delivery.json`：`native_started=false`、分类非飞行——交付收据不得被读作飞行/验收记录。

## 7. 开放风险（显式，不代办）

1. **行号缝**：被绑定文件两处行号锚（`:1097`、`joint_profile.py:219-220`）与其快照/HEAD 不符（§4）；后者同时存在于 tracked plan §5。引用须改用内容锚（`:1187/:1195`；`joint_profile.py:276`）。
2. **untracked 比较器产物目录**：`validation/coordination/gc-diagnostic-comparator-20260912/`（两份 self-check JSON）磁盘存在、未入库；tracked plan §6 引用的输出文件名是 `self-check-7bdfxkb-manager-gc.json`。入库与否由当前权威裁决，本登记不代办。
3. **HEAD 源缺失/漂移**：`tools/manager_gc_candidate.py`、`validation/test_manager_gc_candidate.py` 不在 HEAD，runner 已漂移——任何"重跑 23/23"都必须声明其针对的 SHA 对象，否则无意义。
4. **无因果**：C1 与 24.33 ms stall 的因果未被任何 tracked 件证明；比较器 `claim_limits` 明示两场只说明共现。
5. **受保护文件现状**：`docs/Prometheus.gitmodules.reference`（现场 SHA256 `5aa703020961433befcb2f74cd0432e14fbba139db1fd0616b34c6abf0223855`）与 `validation/coordination/short-cycle-dispatches.json`（`06e65cc1cd7d3aa467740f586e92d5e1de00cc973c07db49694c2c6a73862838`）在本登记时刻为工作树脏文件；本登记未触碰，其后任何漂移与本登记无关。

## 8. 不声称清单（显式）

- 未把历史语境升格为当前执行、验收、批准或收口；
- 未声称 23/23 对当前树有效；
- 未声称 D3 已修复或 C1 已被任何独立结论支持/否证（tracked 记录是"效应不可复现 + 无性能通过输出"，非验收结论）；
- 未重跑 23/23、17 项比较器合同测试或任何诊断场/正式场；
- 未修改被绑定文件或任何 tracked 文件；未触碰受保护文件；未联网；未提交 Git。

## 9. 生命周期判定修订（伴生测试，2026-09-14）

伴生测试 `validation/test_codebuddy_gc_freeze_context.py` 的候选生命周期判定（A pre-admission / B precommit / C postcommit）于 2026-09-14 修订：

1. 原祖先测试对当前 HEAD 的逐字节相等断言（与 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` 比较）被移除，改为 fail-closed 的 `git merge-base --is-ancestor 31e5b65f5448c5558450d16d0f46da0ef0f0a03c HEAD`（exit 0 必须成立；非祖先或无效对象名的任何非零退出一律拒绝，附非祖先负例）。`31e5b65f` 由此定位为**写作时历史基线/祖先**，而非精确 HEAD 钉：其后的不相关提交不再使绑定失效（修订时点 HEAD 为 `438ab764c0cf70f9e017cfbd82aeb04255282e3a`，该命令对其验证成立）。
2. 逐字节权威不变：被绑定 review 文件（`64d0e876…` / 10594 bytes）、§2 三份源快照、runner 漂移边界（`c8577093…` / 79221 bytes）、自 `31e5b65f` 起未漂移的 tracked HEAD 锚（plan/比较器/C1 决策件等），以及本文件自身字节（NOTE SHA256/大小由伴生测试绑定，随本节修订重绑）继续按字节执行。
3. A/B/C 生命周期语义原样保留：pre-admission（三候选既不在 HEAD 也不在 index）、precommit（三候选 stage 0 且 index blob 与工作树逐字节一致、不在 HEAD）、postcommit（三候选入 HEAD 且 HEAD=index=工作树逐字节一致）；部分/混合出现、非零 stage、字节不符仍被拒绝。postcommit 只要求候选字节进入当前 HEAD 并三方一致，不要求 HEAD 等于写作基线。
4. 本节仅为登记维护：不构成任何新的执行、批准或收口含义；未重跑任何诊断场/正式场；未触碰受保护文件；未提交 Git（真实仓库；验证所用临时索引与 scratch 克隆均为仓库外一次性工件，用后删除）。
