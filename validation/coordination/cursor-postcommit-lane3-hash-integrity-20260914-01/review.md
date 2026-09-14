# Lane 3 — 176 + 7 addon SHA256 / 证据可复现 / 秘密 / 大文件 / 目录依赖

2026-09-14。推送后三路验证的第三路。只对已绑定的 `<FINAL_HEAD>` 做 `git cat-file blob` 原始字节核验。
**未运行 pytest/unittest。未走六提交父链。未跑 native / 构建 / 飞行 / #83。**
**未改 blob。未 add / commit / push。不关闭任何 issue / gate。**
写入仅在 `validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/**`。
扫描器只存在于可弃用临时目录，本输出目录不留脚本。

**裁决：PASS。** A 176/176；B 7/7；C `secret_hits=[]` 且卫生/大文件绿；D 目录与 SOURCE 依赖仍在，related 三条未入库。

这不是 owner 批准。`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。

## 派发

```text
工作类别：postcommit-lane3-hash-integrity
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-postcommit-three-lane-verification-plan-20260914-01、
      path-hashes.json、exact-addon-paths.txt、169 content-safety 词表
module / interface：无产品代码变更
独占写入：validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/**
依赖（只读）：176 路径神谕、7 addon、SOURCE 规划/预算/G1 钉
验证：FINAL_HEAD 原始 blob SHA-256；秘密/卫生/大文件；目录依赖存在性
范围外：pytest/unittest（Lane 2）；六提交父链集合比较（Lane 1）；
        native / model / MATLAB / ROS / DDS / SITL / FC / UE /
        构建 / 飞行 / #83；主仓 add/commit/push；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本路在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | 值 |
| --- | --- |
| `<SOURCE_HEAD>` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| `<FINAL_HEAD>` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `<FINAL_TREE>` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `origin/main` (`git ls-remote`) | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `<COMMIT_F>`（任务卡给定，本路不重走父链） | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| 架构祖先退出码 | 0 |

`git ls-remote https://github.com/unununnnn/wksim.git refs/heads/main` 恰好一行，40 hex，且 `<FINAL_HEAD>` ≠ `<SOURCE_HEAD>`。
哈希全部来自 `git -c core.autocrlf=false cat-file blob <FINAL_HEAD>:<path>` 的原始字节，未经文本管道改写 CRLF。
演练私有 `commit-tree` SHA 未当作 `<FINAL_HEAD>`。

源清单自身未漂（不在 176 内，SOURCE 侧只读）：

| 文件 | SHA-256 | 命中 |
| --- | --- | --- |
| `cursor-five-commit-order-path-isolation-audit-20260914-01/five-groups.json` | `a8dcbe245d0fd5305eb3ba027572d9379e4df9a4b7a0f7090723263fabb4848d` | 是 |
| `cursor-final-receipt-ingest-minimization-20260914-01/exact-addon-paths.txt` | `e5b209aac481ee266909b6b1e87dc25717d5ef8e36837da1692be366d33ace17` | 是 |

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| A 176/176 SHA-256 与字节 | **PASS** | missing=[]；hash_mismatch=[]；bytes_mismatch=[]；组计数 34/26/60/17/32/7 |
| B 7 addon + SHA256SUMS 自洽 | **PASS** | 7/7；自身钉 `166b9e9a…`；清单 6 行全命中；清单不列自身 |
| C 秘密 | **PASS** | `secret_hits=[]`；字段名 `token` 记为诊断标识，不是凭证 |
| C 卫生 | **PASS** | 无 NUL；无 zip/tar/gz/7z/rar/pyc magic；无 vendor/pycache/TEMP 路径 |
| C 大文件 | **PASS** | 精确 SHA 重复 0；≥8 KiB 同尺寸对 0；两份已知大账本字节钉命中 |
| D pid 目录 | **PASS** | `git ls-tree -d --name-only` 给出 `validation/pid-final-px4-20260909` |
| D cited_sources | **PASS** | 83 条路径均存在，其中 76 blob + 7 tree；missing=[] |
| D G3 SOURCE 规划依赖 | **PASS** | evaluator / admission / bspline 及 postrepair3 只读绑定仍在 |
| D budget/frame PIN | **PASS** | PIN_PATHS 13、EXPECTED_PINS 23，均 SOURCE+FINAL 存在 |
| D G1 七行产品源 | **PASS** | 七行均在 FINAL，且 SHA-256 与 SOURCE 钉一致 |
| D related B1/B4 三条未入库 | **PASS** | 三处 `git cat-file -e` 退出码均为 128 |
| 未跑测试 / 未改 git / 不关闸 | **PASS** | `claims_owner_approval=false`；输出目录无脚本 |
| 本路总体 | **PASS** | A+B+C+D 全绿 |

失败门：无。

## A. 176 pins

神谕：`validation/coordination/cursor-final-176-six-commit-private-rehearsal-20260914-01/path-hashes.json`。
对 `paths[]` 每一条：`sha256(blob)` == `expected_sha256` 且 `len(blob)` == `bytes`。

PASS：176/176。missing=[]。hash_mismatch=[]。bytes_mismatch=[]。
按组：A 34、B 26、C 60、D 17、E 32、F 7。

## B. 7 addon（组 F）

| 路径 | SHA-256 | 命中 |
| --- | --- | --- |
| `…/SHA256SUMS` | `166b9e9acec1a0bfe7278b44e3746bb3d05fc255b7008155e610d3a5456307a6` | 自身钉 |
| `…/review.md` | `fe8594105b323fd5d01733b8855ad142b1552be2aff47a070a367f5d6ea89940` | 清单行 |
| `…/review.json` | `e5d9255cd7bd66a8e37fc0bb71f095650294ce701dea0027b9a718c367c80ed9` | 清单行 |
| `…/sequence-matrix.json` | `e5af8dd647789ef79e027954cd08998d62f82e76dbeb33661e49ff00f884d511` | 清单行 |
| `…/candidate-hashes.json` | `6b7293e3a310e3312bb676e74409d83e1765943e418a5940d96457384b97715e` | 清单行 |
| `…/dependency-check.json` | `be3f3c74c491aa63f27e4e40ed677f66878d3083603034f9601d398f80f51466` | 清单行 |
| `…/durable-evidence-manifest.txt` | `a644faa044844516d787cd5162edff6a700963c4e4706c64fdb2f44265c64398` | 清单行 |

`SHA256SUMS` 不列自身，这是预期。6 行正文重算全部命中。PASS：7/7。

## C. 秘密 / 卫生 / 大文件

词表与 169 content-safety 同族：私钥块；AWS / GitHub / Slack / Google / Stripe / npm 令牌；Authorization；JWT；连接串口令；`password=` / `client_secret=` 赋值。

- `secret_hits=[]`
- 字段名 `token` 只出现在 `validation/coordination/cursor-g6-budget-related-source-final-review-20260914-01/hostile-delta.json`，是诊断标识，不是凭证
- 卫生：176+7 路径无 `node_modules` / `vendor` / `site-packages` / `__pycache__`，无 `%TEMP%` / `/tmp` / `scratch` 段；正文无 NUL、无压缩包/pyc magic
- 精确 SHA-256 重复 = 0；≥8 KiB 同尺寸对 = 0
- 已知唯一大账本：`validation/e0-budget-approval-provenance-20260914.json` 285820；`validation/full-original-ac-gap-ledger-20260914.json` 225429

发现列表只写规则类别与仓库相对路径，不写主机绝对路径值。

## D. 目录 / HEAD 依赖

必须仍在 `<FINAL_HEAD>`（已在 `<SOURCE_HEAD>`，六提交不得删除）：

- `validation/pid-final-px4-20260909`：目录存在。本路不重跑 `test_cited_sources_exist`
- Full 账本 `cited_sources`：83 条路径均存在，其中 76 blob + 7 tree；`git cat-file -e` 全为 0
- G3 SOURCE 规划依赖仍在：`ego_evaluator.py`、`ego_scene_admission.py`（封印 `f88fa9c6…`）、`ego_bspline_bridge.py`、`validation/ego-planner-static-20260912-02/bspline.json`（`d4d318cc…`）、`planner_scene_binding.py`
- budget `PIN_PATHS` 13 条、frame `EXPECTED_PINS` 23 条，均 SOURCE+FINAL 存在
- G1 七行产品源仍在，SHA-256 与 SOURCE 钉一致

related B1/B4 前沿三条 **不在** `<FINAL_HEAD>`（不属于 176）：

| 路径 | `cat-file -e` |
| --- | --- |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/review.md` | 128 |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/frontier.json` | 128 |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/owner-input-template.json` | 128 |

## 非声称

不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full，不批准 owner 项，
不改判既有 PASS/FAIL，不授权 add / commit / push，不把本路写成代表测试或飞行验收。
未运行测试。主仓无 git 变更。本文件不是 commit。

**PASS。**
