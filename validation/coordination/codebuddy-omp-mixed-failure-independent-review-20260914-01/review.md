# CodeBuddy 独立审查 · OMP mixed 场失败历史语境批次（2026-09-14）

审查者：独立 CodeBuddy evidence reviewer。基线 HEAD `011818876c1b94875fd67cedaaa73abfac866633`
（"Bind OMP delivery diagnostic context offline"，2026-09-14 17:28:22 +0900），审查全程 HEAD 未变。
本审查为离线证据审计：未修改/暂存/提交/推送任何文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；
未重跑 #83；未查询或改动 GitHub；未触碰 `docs/Prometheus.gitmodules.reference` 与
`validation/coordination/short-cycle-dispatches.json`（未读、未列、未改）。

## 1. 范围与字节绑定（全部现场重算，与任务给定值逐字一致）

| 候选 | SHA256 | bytes | git 状态 |
| --- | --- | --- | --- |
| `docs/coordination/omp-mixed-failure-review-20260913.md` | `2417c299d57ccdc79b7368e03180bd0b767aabb91c012257e1443a17fca331c3` | 4448 | 未跟踪 `??` |
| `docs/coordination/omp-mixed-failure-ingest-note-20260914.md` | `92f8adf24faf0ba924ed402c2f07a4b0a2ef68f2583639f38e8f1a7bd67862a4` | 9762 | 未跟踪 `??` |
| `validation/test_omp_mixed_failure_context.py` | `e13cfc72d44a4cd878f77ad3a95abcacea4003859c6458aa0f8f0000cef5f9fd` | 15148 | 未跟踪 `??` |

三份候选均为未跟踪工件（与批次"离线语境绑定"性质一致）；测试套件不要求候选保持未跟踪
（见 §5 暂存运行）。

## 2. 历史/当前边界

- ingest note §0 只做两件事：字节绑定历史语境 + 登记取代/漂移；显式声明自身与被绑定文件
  均不构成 #83（或 #9/#26/#29/#62/#102）的验收/批准/收口/复核/重跑许可。
- 绑定文件自述 2026-09-13；note 以"historical context only / 非权威"定性，要求一切"当前
  是否满足/是否可关闭"判定由当前权威基于当下工件重新作出。审查确认无任何历史语境被提升
  为当前批准或验收。

## 3. 拓扑与写作基线声明（note §开头）逐项核验

- `git merge-base --is-ancestor e2ecd62e914e075d0d9e40eef8ea9c034b958d2f HEAD` 退出码 0 ✓
- `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 0 ✓
- `git rev-list e2ecd62e..011818876 --count` = **1** ✓；该提交（01181887）`diff-tree` 恰为
  **11 个** OMP 交付门/诊断入口语境文件（两份 2026-09-12 历史文档、其 ingest note、
  `validation/test_omp_delivery_diagnostic_context.py`、独立审查目录三件、语境清单目录四件），
  与本批三候选及全部锚点**不相交** ✓，且不含两份受保护文件 ✓。

## 4. 重定位、pins、严格 JSON、算术/latch

- **重定位**：`validation/current-mixed-20260913-01/` 不存在 ✓；字节相同的 tracked 工件在
  `validation/33-formal-promotion/current-mixed-oxv29042/main-rate-analysis.json`，
  SHA256 `b4c7f44e12f96ac63b720b217cd102afeba5c846b3ecbf41c6e4dbd275c410cc` ✓；note 将其登记为
  "路径漂移登记"，要求引用回到 tracked 路径 ✓。
- **bundle 锚**：`bundle-manifest.json`（`f316862f37e6c8997543ef08d03247223c991553919c53152516ee90f804b546`，
  4153 bytes）与 `rate.jsonl.gz`（`8058ecff7f4730d5fd81a50e8817a8a4190230cc2de3b8170496e46e279c99da`）
  均 tracked；bundle 目录 tracked 文件恰 **20** 个 ✓。manifest 严格 JSON（拒绝重复键/非有限常量）
  解析通过，逐字 pin：run `joint-public-flight-oxv29042`、epoch `18c96a7e0af9477092aa87e18239c23c`、
  trace `8725b63c568783199b4a5e7d3de7df532003749b73d4c255131da4bcedee8b91`、analysis `b4c7f44e…`、
  `status=failed`、`RateUnmet('rate_unmet/resource_insufficient')`、`mixed_capability_proof="missing"`
  （与 MISSING 行一致）、`raw_root=/root/wksim-release-acceptance-fe3/...`（外部 WSL 侧）。
- **analyzer/epoch**：`tools/analyze_joint_rate_intervals.py` SHA256
  `1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7`（现值重算一致）✓；
  epoch `18c96a7e` 在 manifest 与 analysis 均在场 ✓。
- **数值锚**（main-rate-analysis.json 严格解析后全部在场）：anchor tick 40 / wall
  `110030174978`；分区 249/975,731、1/4、32,679/98,805,073；creep 合计 99,780,808；
  work_over 15,139,984；latch lateness 100,034,744 @ tick 131,760；完成组端 32,930；
  闭链项 115,732 / 138,204；最大区间 5,547,162 / 5,140,957 / 406,205；门超额 34,744。
- **算术/latch 全部精确闭合**：975,731+4+98,805,073 = 99,780,808 ✓；115,732+99,780,808+138,204
  = 100,034,744 ✓；5,140,957+406,205 = 5,547,162 ✓；(131,760−40)/4 = 32,930 ✓；
  100,034,744−100,000,000 = 34,744 ✓；`steady_after_ns` 112,030,174,978 − anchor wall
  110,030,174,978 = 2.0 s（review "anchor+2.0s 实算" ✓）。
- **xtj8wk8i 分类（untracked，按 note §2.3 仅声明收存）**：目录
  `validation/33-formal-promotion/20260913-mixed-failure-review/` 确为 gitignored（`.gitignore:53`）。
  `xtj8wk8i-probe-classification.json`（严格解析通过）逐字支持 review 数字：入选 894 组 /
  71,821,720 ns；睡眠越界合计 56,629,628 ns、组均 63,344 ns（≈63.3µs）、最大 1,269,606 ns
  （≈1.27ms）、>1ms 仅 1 组；`final_spin_other` 中位 1,036,079 / 最大 1,399,275；
  零睡眠组 2 个 / 超额 315,935 ns（≈0.32ms）；`residual_note = "removed: the difference is
  not an attributable residual…"`（与 §3.2 撤回一致）；boundary_proof 与 review "全部位于
  initial_health_end 与 terminal 释放之间"一致；trace 路径在外部 `/root/...` 侧。

## 5. 两项撤回、门、外部边界、#83

- **撤回 1（tick≤2040 墙钟分区作废）**：review 原文在场（"已作废"），note §3 登记并禁止复活
  tick 域分区 ✓。
- **撤回 2（v1 "15.19ms 已归因残余"撤回）**：review 原文在场（"已撤回"），note §3 登记，
  分类工件 `residual_note` 记 `removed` ✓。
- **门**：1 ms tick、4-tick 组、no-catch-up、100 ms lateness 门、全窗、run 内单调差分、
  禁止跨 run 原点相减、禁止追赶/回填、不得叠加重叠区间、身份门、物理门、`land_accepted`
  未达终态不得计 pass —— 全部在 note 绑定字节内，未被削弱 ✓。
- **外部 WSL 区分**：note §4 将 raw 场目录/live 目录/实验区/PGID 进程态列为检出外、临时态、
  仅声明收存；bundle manifest 的 `raw_root`/`live_root` 为 `/root/...` 印证该区分 ✓。
- **#83**：绑定文件称"诊断证据，MISSING"；note §5 明示"诊断场永不得充当 #83 通过证据；
  本绑定全程未重跑 #83，不授予任何重跑许可"。审查套件的 promotion 正则对 note 与 review
  均无命中；测试负例对 5 类批准措辞全部拒绝 ✓。本审查亦未重跑 #83、不授予任何许可。

## 6. 测试运行（非 native 离线 unittest）

- **run 1（正常工作树，真实 index 未动）**：`python validation/test_omp_mixed_failure_context.py`
  → **20/20 OK**（0.517s，0 failures / 0 errors，exit 0）。
- **run 2（临时 `GIT_INDEX_FILE` 精确三文件 staging）**：`git read-tree HEAD` 后
  `git add` 恰好三份候选；临时 index 与真实 index 的 `git ls-files` 差分**恰为 3 行新增**
  （总计 10,748 项）；在该临时 index 下复跑套件 → **20/20 OK**（0.450s，exit 0）。
  临时 index 文件已删除。
- **真实 index 不变**：`git ls-files -s | sha256sum` 前后均为
  `944e3ef9d5ccb574a46ecbc8a1245a9b7c53de5d08185014227e50dbf4c8e2f9` ✓。
- 测试设计核验：仅祖先断言（不锚 HEAD 相等）、路径全部经 `__file__` 解析、无写入、无网络、
  无 native 执行、不读取 untracked 分类工件（其登记只对 note 字节断言）。

## 7. 发现（P1=0，P2=0，P3=4）

- **P3-1** `omp-mixed-failure-review-20260913.md` §"可复核的下一诊断问题"："稳态 ~2.9µs/区间
  的持续 release 超额"未标口径。按 tracked 数值可导出：release_excess_total 84,640,824 ns /
  32,679 稳态区间 ≈ 2.59µs；creep 99,780,808 ns / 33,508 全部区间 ≈ 2.98µs。"~2.9µs"量级正确、
  带 "~" 且属历史语境，不阻塞，但引用时应注明口径或改用可导出值。
- **P3-2** review "睡眠请求 2,050.6ms vs 实睡 2,107.3ms"两个字面量在本检出任何工件中不存在，
  仅有其差 56.7ms 与分类 JSON 越界合计 56,629,628 ns（≈56.63ms）在舍入内一致。该节已由
  note §2.3 按"untracked 工件、仅声明收存"覆盖，但逐字节不可本地复核，引用时须携带该限定。
- **P3-3** review §xtj8wk8i 标题括注"同场同身份"存在歧义：xtj8wk8i epoch 为 `792e1feb…`，
  与 oxv29042 epoch `18c96a7e…` 不同（分类 JSON trace/epoch 佐证其为独立诊断场）。节标题
  已具名 xtj8wk8i，无事实混淆，但"同场"易被误读为同 epoch 同场，引用时宜展开表述。
- **P3-4** `test_omp_mixed_failure_context.py:169` `import re` 位于 `assert_no_promotion`
  使用点（:165）之后。运行时安全（模块级 import 先于任何测试调用执行），且带 noqa 注释，
  但属易碎风格；后续维护者上移使用点或重排 import 时可能引入 NameError。

## 8. 结论

**PASS**（P1=0、P2=0；仅 4 项 P3）。全部重算哈希、tracked 锚、内容 seam、算术/latch 闭合、
两项撤回与 residual 移除登记、外部 WSL 区分、1ms/4tick/no-catch-up/100ms/全窗门、#83 冻结
措辞与两轮 20/20 测试结果均与候选声明一致。本审查不构成任何批准、验收或收口；历史语境
不得据此提升为当前权威。

SHA256SUMS 仅列本目录 `review.md` 与 `review.json`；本目录与三份候选均未暂存/未提交。
