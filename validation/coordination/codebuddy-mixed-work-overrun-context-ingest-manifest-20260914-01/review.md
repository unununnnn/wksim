# Ingest manifest · CodeBuddy mixed-work-overrun 历史语境批次（2026-09-14，context-only）

Owner：codebuddy-ingest-manifest。manifested HEAD
`438ab764c0cf70f9e017cfbd82aeb04255282e3a`（会话起止两次复核，写作全程未变）；independent
review -01 的 reviewed HEAD 为 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`，二者不要求相等：
reviewed HEAD 是 manifested HEAD 的祖先（`git merge-base --is-ancestor` 退出码 0），
区间内 `git rev-list --count 31e5b65f..438ab764` = **2** 个提交，且架构连续性锚
`f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 亦为当前 HEAD 祖先（同法复核，退出码 0）。
schema `wksim.ingest-manifest.v1`；scope `context-only`；acceptance `non-acceptance`。

本 manifest 只把独立审查终态 **KEEP（P1=0、P2=0、P3=1）** 的三件候选（remediated
mixed-work-overrun v2 源文档 + 其绑定/登记 ingest note + 离线绑定测试）连同其独立审查三件
（-01）与本 manifest 四件输出，按字节收存为**历史语境批次**。它不构成 #83（或 #84/G6/Full
或任何工单）的验收、批准、收口、复核或重跑许可；不关闭 G6、不关闭 Full、不收口 #84、
不触发 #83 重跑、不做任何验收晋升；不授予任何当前速率门状态；不产生任何 native 结果或
飞行证据；不把历史语境提升为当前权威。一切"当前是否满足 / 是否可关闭"的判定由当前权威
（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 0. 批次构成与排除

- 精确批次 = 3 候选 + 3 独立审查输出 + 4 本 manifest 输出 = **10 路径**（§2）。
- 保护/无关路径**排除且未触碰**（未读改、未暂存）：`docs/Prometheus.gitmodules.reference`、
  `validation/coordination/short-cycle-dispatches.json`。#83 及其诊断场目录不在本批次，
  本会话未重跑、未触碰。其它批次的全部 review/manifest 目录均不在本 10 路径批次内。
- 本会话未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未联网；未提交/暂存到
  真实 index；未 push。

## 1. 源 M 生命周期与 tracked-anchor 限度

- **源 M**：`docs/coordination/mixed-work-overrun-20260913-v2.md` 在 HEAD `438ab764` 树中
  仍为修订前版本（blob `24ad15729ac393026488f9356f265297a8b4b071c92ab6a501b0fe45bca4893a` /
  2863 bytes，本会话经 `git show HEAD:<path>` 重算确认）；工作树字节为修订版
  `b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352` / 5410 bytes（现场重算，
  与任务给定值一致），`git status --porcelain` 记 ` M`（tracked modification，未暂存）。
  **本绑定针对工作树字节**；修订是否入库由当前权威裁决，本 manifest 不代办。在其被提交前，
  对该路径的任何暂存/提交动作都会使 HEAD 树版本进入 `24ad1572…` → `b432e2c3…` 的 M 演进；
  本 manifest 的 expected staged delta（§3）即按此 M 语义计。
- **tracked-anchor 限度**：套件的全部内容断言锚定于已跟踪锚的 HEAD 树字节
  （analyzer `1162d9fb…`、v2 JSON `e10619cc…`、v1 doc/JSON、crosscheck、rate.jsonl.gz、
  joint.py `:54` 门控点、frozen runner 快照、ds-g0-g5 audit 门控原句）与两个候选的工作树
  字节；**无 PASS 依赖任何仅外部（untracked-only）原件**（raw wire、go.json、
  experimental-admission.json 在 oxv29042 场目录 HEAD 树与磁盘均缺席，只能在外部接受根核对，
  本地不可复验）。
- **历史遍历 P3（F-1，环境性、先在）**：本仓库为 shallow clone 且带大量
  `refs/codex/turn-diffs/checkpoints/*` 引用指向 shallow 边界之外的对象，无限制的
  `git log --all -S"e5a0db2b"` 以 `fatal: unable to read d12de5b5…` 中止。故
  "e5a0db2b… 从未提交"的结论只在**可完成的路径限定历史**内证明（analyzer 全历史恰一个
  提交 `596cb5e6`、内容 `1162d9fb…`，套件同法 exit 0），本 checkout 内无法加强为无限制
  全仓库 pickaxe。非本批次引入，不使任何批次主张失效。

## 2. 精确路径集合（10 个唯一排序路径 = 3 候选 + 3 独立审查输出 + 4 输出）

`exact-paths.txt`（SHA256
`c17890a97d15255cef65511734e0dac1b632ef47c33f22c8509d42220dffe9e7`，869 bytes）恰列
10 行、唯一、bytewise（`LC_ALL=C sort -c` 通过）排序、LF 结尾无 CRLF：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/codebuddy-mixed-work-overrun-ingest-note-20260914.md` | 候选：绑定与登记 ingest note |
| 2 | `docs/coordination/mixed-work-overrun-20260913-v2.md` | 候选：remediated 源文档（tracked M，工作树字节） |
| 3 | `validation/coordination/codebuddy-mixed-work-overrun-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 4 | `validation/coordination/codebuddy-mixed-work-overrun-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 5 | `validation/coordination/codebuddy-mixed-work-overrun-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 6 | `validation/coordination/codebuddy-mixed-work-overrun-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 7 | `validation/coordination/codebuddy-mixed-work-overrun-independent-review-20260914-01/SHA256SUMS` | 独立审查校验和清单 |
| 8 | `validation/coordination/codebuddy-mixed-work-overrun-independent-review-20260914-01/review.json` | 独立审查记录 |
| 9 | `validation/coordination/codebuddy-mixed-work-overrun-independent-review-20260914-01/review.md` | 独立审查报告 |
| 10 | `validation/test_codebuddy_mixed_work_overrun_context.py` | 候选：离线绑定测试 |

## 3. expected staged delta（9 A / 1 M / 0 D）

以当前 HEAD 树为基（temp index `git read-tree HEAD`），`git add -f` 恰 §2 所列 10 路径后：

- **1 M**：`docs/coordination/mixed-work-overrun-20260913-v2.md`（HEAD 树 `24ad1572…` →
  工作树 `b432e2c3…`）；
- **9 A**：ingest note、测试、独立审查 -01 三件、本 manifest 四件（当前 HEAD 树均无此
  9 路径，`git ls-tree -r HEAD` 核实）；
- **0 D**：无任何删除。
即 `git diff-index --cached --name-status HEAD`（temp index 语义）= 恰 10 行、9 `A` + 1 `M`。

## 4. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| mixed-work-overrun-20260913-v2.md（工作树） | `b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352` | 5410 |
| codebuddy-mixed-work-overrun-ingest-note-20260914.md | `1648f3d486e3e9bfe42632c39efaf4976237385be3703dc0903a4885bec6c575` | 9531 |
| test_codebuddy_mixed_work_overrun_context.py | `a510bd6aac8fd96f779e234b5be4b2974e66909a75ad7dde3bc150f86882450b` | 25557 |
| -01 review.md | `901f3b05d9ba227a4b450de3fb7767f619dd79a59342af80fb4b137f01541929` | — |
| -01 review.json | `a1916cbdb9c2d3da33302e62ef10c645332ad0a837e308696ee7af1815621979` | — |
| -01 SHA256SUMS | `71f65bcc1c60f24011d54c3cd2e0136424c4b23aa939e5639ae3e72d819fd498` | — |

- 6 输入哈希与给定字节数均现场重算，与任务给定值逐字一致；6 输入本任务全程未修改。
- -01 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，
  退出码 0。
- -01 `review.json` 严格解析通过：`head.observed = 31e5b65f…`（与写作时一致）、
  `verdict=KEEP`、`P1=0、P2=0、P3=1`、`real_index_byte_identical.identical=true`。

## 5. 独立审查 -01 终态（本 manifest 不改判）

-01 判定 **KEEP**（P1=0、P2=0、P3=1）。一项 P3 原样登记：

1. **P3-1（F-1）**：shallow clone + shallow 边界外 checkpoint refs 使无限制
   `git log --all -S` 遍历中止；"e5a0db2b… 不在 Git 中"只在可完成的路径限定历史内证明
   （恰一个提交 `596cb5e6`，内容 `1162d9fb…`）。环境性、先在、非本批次引入，
   不使任何批次主张失效（§1 详）。

-01 的全部边界与非主张原样承继：历史诊断证据仅限、`full_run_acceptance=false`、
`performance_pass=false`、`native_executed=false`、外部件不可本地复验、v1 历史 /
v2 权威边界、launch.sh:4 显式 unset 控制、527 反证下界、7 组 × 17 tick 窗口普查。
本 manifest 原样保留该定性，**不提升、不改判、不构成任何批准**。

## 6. 测试事实

- **run 1（normal）**：`python -m unittest
  validation.test_codebuddy_mixed_work_overrun_context -v`，正常工作树、真实 index 未动 →
  **Ran 29 tests, OK (skipped=1)**，0 failures / 0 errors，exit 0；skip 为
  `TestTemporaryIndex`（无 `WKSIM_MIXED_OVERRUN_TEMP_INDEX=1` 时按设计不激活）。
- **run 2（temp index，恰 10 路径）**：repo 外临时 `GIT_INDEX_FILE`（`mktemp -u`
  非存在路径 `/tmp/tmp.GgJuif45kh`，git `read-tree HEAD` 创建）→ `git add -f` 恰
  exact-paths.txt 所列 **10 路径** →
  - `git diff-index --cached --name-status HEAD`（temp index 语义）= 恰 10 行，
    **9 `A` + 1 `M`**（1 M = 源文档 `24ad1572…` → `b432e2c3…`），0 `D`；
  - temp index 与真实 index 的路径集差 = **恰 9 条新增、0 条移除**；
  - 10 个批次路径的 staged 条目**全部 stage 0**（套件对整个 temp index 断言无任何
    非 stage-0 条目，通过）且**逐个 blob 等于工作树字节**（`git hash-object` 逐路径
    比对 10/10 OK）；
  - `git diff --name-only` 限定 10 批次路径 = **空**（diff-check clean）；不限定时额外
    列出两个保护脏文件（`docs/Prometheus.gitmodules.reference`、
    `validation/coordination/short-cycle-dispatches.json`）——二者在本会话前即对 HEAD
    脏，不属本批次，temp index 自 HEAD 播种故显现，非本任务扰动；
  - 套件 `WKSIM_MIXED_OVERRUN_TEMP_INDEX=1`：**Ran 29 tests, OK**，29/29，0 skipped，
    exit 0（含 `TestTemporaryIndex` 断言两候选 stage 0 / mode 100644 / blob 等于工作树
    字节）；
  - 临时 index 用后删除（`rm -f`，复核不存在）。
- 真实 index 完整性：`.git/index` 文件字节哈希 run 前
  `327b22366c0ba7cb1e3fbddc8cd41023541b92f3cea745af754aba1b41862976`、run 后相同；
  `git ls-files -s | sha256sum` 前后均
  `5de63e159c44d37a72acfecee8c178ab154b80b00d36cb9130588e9042f5a8ef` → 真实 staged
  集合逐字节不变、全程未暂存。`git status --porcelain`：本 manifest 四件输出创建前
  18 行（哈希 `bdbe7fe887f7f0caefdcfff7ef2431ea90efebc9ded5463c0b112ac504736d27`）、
  创建后 19 行（哈希 `9edc0672fa3d8e0d3010c793d6bcdeb68a1681f0afd244826aa592e5ecec4c91`）；
  **该 1 行增量由并发第三方会话**新建 `validation/test_codebuddy_native_wait_contract_context.py`
  （mtime 2026-09-14 21:03:31，落在本会话窗口内）造成，不属本批次、本任务未读改未暂存；
  本任务输出全部位于 gitignore 覆盖的 `validation/coordination/`，不出现在 status 中，
  对 status 零扰动。HEAD 会话起止均为 `438ab764…` 未变。
- 自指说明：run 2 执行时本 review.md/review.json 的 run 结果字段仍为 PENDING 占位、
  SHA256SUMS 为中间版本；staged-index 契约测试只绑定两候选（ingest note + 测试）blob
  （与工作树字节逐字一致、全程未变），且 10 路径集合相等断言与 9A/1M delta 断言均与
  字节无关，故恰 10 路径收编对最终输出字节同样成立。SHA256SUMS 覆盖最终态的
  exact-paths.txt / review.md / review.json，不含自身哈希。

## 7. 边界与非主张

- 未修改任何输入或输出目录之外的文件；未暂存到真实 index、未提交、未推送（真实 index
  全程未动）；无 reset/clean。
- 未触碰 §0 所列保护路径；#83 未重跑；其它批次目录未触碰。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未联网。
- 门与措辞原样保留（1 ms tick、native barrier、4-tick grouping、no catch-up、100 ms/全窗、
  physics/identity 门）；诊断场结果永不得充当 #83 通过证据。
- 本批次为 context-only 收编：不授予 #83/#84/G6/Full 验收/批准/收口/重跑、不授予当前
  速率门状态、不产生 native 结果或飞行证据、不把历史语境提升为当前权威；本结果不算
  全场通过。
