# Ingest manifest · OMP G6 first-step 历史上下文批次（2026-09-14 -02，remediation 后，context-only）

Owner：codebuddy-ingest-manifest。manifested HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`
（会话开始实测 `git rev-parse HEAD`，写作全程未观察到变化；与独立审查 -03 的 baseline head
相同，无基线漂移）。schema `wksim.ingest-manifest.v1`；scope `context-only`；acceptance
`non-acceptance`。

本 manifest 只把 remediation 后的绑定 note、两份历史语境文档、离线绑定测试与独立审查 -03
三件套按字节收存为**历史上下文批次**。绑定终态：独立审查 -03 **PASS / ADOPT**，P1=0、
P2=0、P3=1（唯一 P3 非阻塞，见 §3，本 manifest 精确记录、不升格、不执行改动）。其前序
独立审查 -02 与本 manifest 的 -01 版已被 -03 判为 superseded：二者字节身份不被信任，全部
排除在 11 路径之外，仅作历史证据原样保留。本 manifest 不构成 G6 或 Full 通过、不构成 #84
（或任何工单）的收口、不授予 #83 重跑许可（#83 在 -03 期间经 `gh` 实测为 CLOSED、#84 为
OPEN）；不提供任何当前 native/飞行证据；不把历史语境提升为当前权威。一切"当前是否满足 /
是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 0. 基线关系（祖先锚定，HEAD equality 事实成立）

- 本 manifest manifested HEAD = `31e5b65f…` = 会话开始时 `git rev-parse HEAD` 实测值；
  写作全程未观察到 HEAD 前进。
- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor` 退出码 0，本会话复核）。
- 独立审查 -03 的 baseline head 亦为 `31e5b65f…`（见其 review.json `baseline.head`），
  审查基线与本批 manifested HEAD 一致。
- 被取代的 review -02（`validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-02/`）
  与 manifest -01（`validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-01/`）
  按要求**逐字节原样保留为历史证据**，本任务未读改、未纳入本批 11 路径。

## 1. 精确路径集合（11 个唯一排序路径 = 7 输入 + 4 输出）

`exact-paths.txt`（SHA256
`fb45e44a81391b3d2c8ebc0b4cd09d5df1545721b75cd92927e74bb736a5fdbb`，873 bytes）
恰列 11 行、唯一、bytewise（`LC_ALL=C`）排序：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/omp-first-step-comparison-review-20260913.md` | 历史语境对比文档（精度修正版） |
| 2 | `docs/coordination/omp-g6-first-step-ingest-note-20260914.md` | 绑定与登记 note（remediation 后） |
| 3 | `docs/coordination/omp-reference-first-step-review-20260913.md` | 历史语境参考审查 |
| 4 | `validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/SHA256SUMS` | 独立审查校验和清单 |
| 5 | `validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/review.json` | 独立审查记录 |
| 6 | `validation/coordination/codebuddy-omp-g6-first-step-independent-review-20260914-03/review.md` | 独立审查报告 |
| 7 | `validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/SHA256SUMS` | 本 manifest 校验和 |
| 8 | `validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/exact-paths.txt` | staging 契约 |
| 9 | `validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/review.json` | 本 manifest 记录 |
| 10 | `validation/coordination/omp-g6-first-step-context-ingest-manifest-20260914-02/review.md` | 本 manifest 报告 |
| 11 | `validation/test_omp_g6_first_step_context.py` | 离线绑定测试 |

## 2. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| omp-reference-first-step-review-20260913.md | `7973f0220c05861547283fbc47f3cfb8e5875a6101023e64593ad7b2664bc17a` | 2979 |
| omp-first-step-comparison-review-20260913.md | `728bce90e0e2da893746e9113954694b6fb7147537db18f564e186dfa5769c14` | 3985 |
| omp-g6-first-step-ingest-note-20260914.md | `c7f034535096047e321ab654fac418d7de5775854ac0e5ff06d97db2369308bc` | 14459 |
| test_omp_g6_first_step_context.py | `ef7e613b0781902a76f5b88ac383510eaa200599a7fb8a4ec7e4c9885eea25cf` | 54340 |
| review -03 review.md | `bd9ddbe4ddec784966819e53d29894cf52935faf25361b6f972dc748c706a169` | 8917 |
| review -03 review.json | `65cb4a8466d1665bed1ea47c48447b03e81b88956644d283a9ce13f997be5fb4` | 6834 |
| review -03 SHA256SUMS | `288de5da0ff23daf3bea36dba8fab508404b013aa1cc16871da52f83ebee3f50` | 154 |

- 7 输入哈希与字节数均现场重算：note 与 test 与本任务给定 pin（`c7f03453…`/14459、
  `ef7e613b…`/54340）逐字一致，其余与 -03 记录逐字一致；7 输入本任务全程未修改（终态
  复hash 同值）。
- review -03 目录 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json
  OK，退出码 0。
- 独立审查 -03 `review.json` 严格解析通过：`baseline.head=31e5b65f…`、`verdict=PASS`、
  `decision=ADOPT`、**P1=0、P2=0、P3=1**、tests=32。

## 3. 独立审查 -03 关键事实（本 manifest 原样保留，不重判）

- **Driver 身份裁决（已由 owner 记录于 note §5/§8，-03 核实其编码完整）**：frozen R1
  driver `7f3bc0c88263a6e1c94a3f42658fe43db2a0b75abca7a5fb59fcfaafdba99cde` 在三处 pin
  位置字节一致且**不可变**；既不授权更新 frozen 副本、也不授权 repo 回填（backfill）；
  该裁决取代先前的 live 两选项措辞（测试禁止六种被取代/破坏性表述）；今后每次 driver
  执行须 launch-time SHA 重算 + executed-bytes 快照。裁决收口范围**仅** owner-ruling
  子工单：不构成 G6/Full 通过。repo 当前 driver `4221246303642b26290b63c118ced5209a6e928a6101140cc00dc4cd12278040`
  （HEAD blob `1cedff93bd8fd48d7e867541ed83423edaa03089`），引入提交 `3f40ba03…`（其父
  `bf3c224e` 处不存在）；frozen 与 current 恰差两行（L137 类型门 `type(x) in (int, float)`、
  L148 `float(...)` 强转）；execution-03 未调用任一 driver（`unused_changed_driver`，
  expected `7f3bc0c8…` vs actual `42212463…` matches=false，非缺陷）。
- **仍开放的限制（原样保留，不因本批收窄）**：36 个刚体状态仅映射 13，**23 个未覆盖**；
  `ode4_stage_mapping` 未逐字验证（开放）；native/全窗证据缺失（timing 锚原样保留：
  1 ms major、no-catch-up、>100 ms 迟到 freeze-with-restore；`omp-mixed-failure-review-20260913.md:59`
  "mixed 能力证明行仍 MISSING"）；无当前 native/飞行证据。
- **ULP 事实（-03 独立重算，此处保留）**：stage 差异链 q s3 derivatives[2]=1、
  derivatives[3]=64、p,q/r s3 cont_states[1]=1、ub,vb,wb s3 derivatives[0]=1；终态
  q index3=**44**、ub,vb,wb index0=1；p,q/r 与 xe,ye,ze 终态零差异；无"后续全 1-ULP"
  规律；全部差异双精度为**正规数**（含 3.46e-47）；值幅 4.95e-18 与 1-ULP 网格增量
  约 -7.7e-34 **二者区分**。
- **唯一 P3（P3-1，非阻塞，按 -03 结论保留不改）**：note §5 证据目录句"101 个跟踪文件，
  无未跟踪残留"在 git 语义上成立（unignored == []，测试断言即此），但 run-01/cache/ 下
  另有 **125 个 gitignored 的 Simulink 构建缓存文件**（`slprj/`、`.slxc`）存在于磁盘、
  未跟踪；读者可能误读"磁盘内容 == 101 文件"。-03 未要求字节改动，本 manifest 不执行
  任何改动、不升格为 P2，仅精确记录。

## 4. 测试事实（本会话运行）

- **run 1（normal）**：`python -B validation/test_omp_g6_first_step_context.py`，正常工作树、
  真实 index 未动 → **32/32 OK**，0 failures / 0 errors，exit 0（Ran 32 tests in 3.871s）。
- **run 2（staged）**：临时 `GIT_INDEX_FILE`（repo 外临时文件；`git read-tree HEAD` 后对
  exact-paths.txt 所列 **11 路径**逐一 `git add -f`）→ 与真实 index 的 `git ls-files -s`
  路径集差 = **恰 11 条新增、0 条移除、0 条内容变更**（11 路径在 HEAD tree 中均未被
  跟踪）；全部条目 **stage 0**，且每条 blob 与工作树文件 `git hash-object` 逐一相等
  （blob-equal）；临时 index 条目数 10777 = HEAD tree 10766 + 11 → **32/32 OK**，exit 0；
  临时 index 用后即删。
- **real index 不变证明**：`git ls-files -s | sha256sum` 操作前后均为
  `5e08ccabec2775053b28f34e44eedd55db1a8b37ef8b4d895023d651f4b835ef`（10766 条），全程
  未对真实 index 执行 add/reset/clean/commit/push。
- **diff-check**：全树 `git diff --check` 的 whitespace 告警仅来自保护文件
  `docs/Prometheus.gitmodules.reference` 的**预存未提交修改**（本会话开始前即存在，非本
  任务产生，属禁止触碰清单，本 owner 未读改）；本批 11 路径均未被 git 跟踪，tracked-diff
  检查对其为空集，无任何本批来源告警。

## 5. 边界与非主张

- 未修改输出目录之外任何文件；未暂存到真实 index、未提交、未推送；未 reset/clean；真实
  index 全程字节不变。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`；未触碰
  `docs/coordination/mixed-work-overrun-20260913-v2.md`（-03 期间观察到的外部并行批次
  漂移，非本批产生）、`docs/coordination/rolling-six-plan-20260912.md`、
  `docs/coordination/claude-native-wait-next-probe.md`、`validation/_probe_delivery_contract.py`、
  `%TEMP%audit26-report.json`；review -02 与 manifest -01 目录未修改、未纳入本批。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；无网络、无 GitHub
  查询或改动。
- 门与措辞原样保留：1 ms tick、native barrier、4-tick、no-catch-up、100 ms/全窗、物理与
  身份门；诊断场永不充当 #83 通过证据；driver 裁决仅收口 owner-ruling 子工单。
- 被取代的 review -02 与 manifest -01 逐字节保留为历史证据（其路径不入本批 11 路径）。
- 本批为**历史上下文收存**：不构成 G6 或 Full 通过，不构成 #84 收口，不授予 #83（或任何
  工单）验收/关闭/复核/重跑许可，不提供当前 native/飞行证据。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入自引用，
  由会话终态报告记录。
