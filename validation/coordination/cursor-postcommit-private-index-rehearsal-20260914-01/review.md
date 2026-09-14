# Postcommit 最终入库清单私有 index 演练

2026-09-14。对已稳定的
alidation/coordination/cursor-postcommit-final-ingest-manifest-20260914-01
六件终稿做私有 GIT_INDEX_FILE 暂存演练。
**未执行源清单 commands.ps1。未执行真实主仓 add / commit / push。**
**未运行 #83 flight、任何测试 / native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight。**
**未改现有文件、主 index 或 refs。**
写入仅在
alidation/coordination/cursor-postcommit-private-index-rehearsal-20260914-01/{review.md,review.json,SHA256SUMS}。

**裁决：PASS。expected_count=33，staged_count=33，extra=[]，missing=[]，deletes=[]，renames=[]。**
这不是一次真实入库。不关闭 Full / G0–G6，不批准 owner 项，不授权 add / commit / push。

## 派发

`	ext
工作类别：postcommit-private-index-rehearsal
         （非新开发、非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、源清单六件
module / interface：无产品代码变更
独占写入：本目录三份回执
依赖（只读）：源清单 exact-paths.txt 33 条
验证：清单非空/排序/无重复/仓库相对且存在；
      GIT_INDEX_FILE=TEMP 唯一文件；read-tree HEAD；
      逐路径 git add -f --；私有 staged 集合=清单；
      staged blob SHA-256=工作树；主 cached 前后空；
      HEAD/refs/两份受保护脏文件哈希未变
范围外：主 index add/commit/push/reset/clean/checkout、
        git add .、改现有文件或 refs、关闭 issue/gate、
        Full / G0–G6、#83 / native / 构建 / 飞行
`

子代理策略要求的 gpt-5.6-luna / gpt-6-astra 不在本界面可选模型列表中。
演练在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 等待源清单

源目录在 poll 3 出现但仍缺文件。poll 7 六件齐但 path-hashes.json 仍在写（11512→11409）。
poll 8 与 poll 9 连续两次大小稳定后才读内容，没有读半写入文件。
间隔不超过 20 秒，总等待 160 秒。

| 文件 | 稳定字节 |
| --- | ---: |
| review.md | 5903 |
| review.json | 18978 |
| exact-paths.txt | 3015 |
| path-hashes.json | 11409 |
| commands.ps1 | 8999 |
| SHA256SUMS | 315 |

## 计数与差集

| 项 | 值 |
| --- | --- |
| expected_count | **33** |
| staged_count | **33** |
| extra | **[]** |
| missing | **[]** |
| duplicates | **[]** |
| deletes | **[]** |
| renames | **[]** |
| modifies | **[]** |
| blob_sha256_mismatches | **[]** |
| forbidden_hits | **[]** |

33 条均为 A（相对 HEAD 新增）。私有 staged 路径序与 xact-paths.txt 完全一致。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 源六件存在且连续两次大小稳定 | **PASS** | poll 8=poll 9；确认时尺寸未再变 |
| 清单非空、排序、无重复、仓库相对且存在 | **PASS** | 33/33 文件；无 ..、无绝对路径、无反斜杠 |
| HEAD 钉死且 f333316 为祖先 | **PASS** | 前后均为 59d8da51…；祖先退出码 0 |
| 私有 read-tree 后再逐路径 git add -f -- | **PASS** | GIT_INDEX_FILE 指向 TEMP 唯一文件；未用 git add . |
| 私有 staged 集合 = exact-paths.txt | **PASS** | extra/missing 空；无删除或重命名 |
| staged blob SHA-256 = 工作树 | **PASS** | 33/33 命中；core.autocrlf=false |
| 主 cached 前后空 | **PASS** | git diff --cached --name-only 均为空 |
| 主 index 内容未变 | **PASS** | 1,586,275 字节，SHA-256 4fc632c9… 前后相同 |
| HEAD / refs 未变 | **PASS** | HEAD / main / origin/main / origin/HEAD 均为 59d8da51… |
| 两份受保护脏文件未变且未入 staged | **PASS** | Prometheus.gitmodules.reference 与 short-cycle-dispatches.json 工作树/HEAD blob 哈希前后相同 |
| 无 captures / TEMP / 未授权路径 | **PASS** | forbidden_hits=[] |
| TEMP 私有 index 已删且未删目录树 | **PASS** | 前缀 leftover=0 |
| 真实 add/commit/push 未执行 | **PASS** | 未跑 commands.ps1 |
| 本审查总体 | **PASS** | 0 P1 |

失败门：无。

## 方法

只在系统 TEMP 创建本任务唯一 index 文件，设置 GIT_INDEX_FILE 到该解析后确认位于 TEMP 下的路径。主仓 .git/index 从未作为 GIT_INDEX_FILE。

1. git read-tree HEAD；私有 cached 空；write-tree = 5d1cbb9e…
2. 按 xact-paths.txt 逐路径 git add -f -- <file>
3. 比对私有 diff --cached --name-only / --name-status 与清单
4. 对每条 staged blob 做 cat-file -p SHA-256，对照工作树文件
5. 再查主仓 cached / index SHA-256 / refs / 两份脏文件
6. 只删除已解析且位于 TEMP 下的该唯一 index 文件，不删目录树

## 明确未入 staged

| 路径/类 | 处理 |
| --- | --- |
| 两处已跟踪脏文件 | 工作树 ≠ HEAD；不在 33 |
| captures / 临时 clone / %TEMP% / %TEMP%audit26-report.json | 不在 33 |
| lane2-cross-review / receipt-ingest-preplan / three-lane-plan-final-review | 源清单排除 |
| lane3 hashes.json | 源清单排除 |
| 其他历史 untracked | 不在 33 |
| 本演练三件 | 不在 33 |

## 发现（P1–P3）

| id | 级 | 标题 |
| --- | --- | --- |
| — | P1 | **无** |
| P2-TWO-LANE2-RECEIPTS-OMIT-CLAIMS-OWNER-APPROVAL-FIELD | P2 | 承继源清单。两份 Lane2 回执缺该字段但不是 true。不否决本演练。 |
| P3-EVIDENCE-FORCEADD | P3 | /validation/*/ 被忽略，必须精确 git add -f --。 |
| P3-UNRELATED-DIRTY | P3 | 两处已跟踪脏文件必须停在当前工作树/HEAD blob。 |
| P3-SUMS-OMITS-SELF | P3 | 本目录 SHA256SUMS 不列自身。 |
| P3-SOURCE-SUMS-OMITS-PATH-HASHES | P3 | 源 SHA256SUMS 只列 4 份；path-hashes.json 自指故未列入。 |
| P3-PRIVATE-ADD-WROTE-LOOSE-OBJECTS | P3 | 规定的 git add -f 会向主对象库写入新 blob；未改 index/refs/现有文件。未删对象。 |
| P3-COMMANDS-NOT-EXECUTED | P3 | commands.ps1 未执行。 |
| P3-THIS-REHEARSAL-NOT-IN-33 | P3 | 本演练目录不进入源清单。 |
| P3-REHEARSAL-DOES-NOT-AUTHORIZE-INGEST | P3 | PASS 只证明私有 staged 集合；不授权真实 add / commit / push。 |
| P3-NO-OWNER-APPROVAL-OR-GATE-CLOSURE | P3 | 不关闭 Full / G0–G6，不是 owner 批准。 |

## 非声称

不关闭 Full / G0 / G1 / G2 / G3 / G4 / G5 / G6，
不关闭 #39 / #102 / #59 / #10 / #60，
不批准 owner 项，不授权 add / commit / push，
不把本演练写成三路 Full 收口或真实入库。
未运行测试、native、构建、飞行、#83。
主仓无 git add / commit / push / reset / clean / checkout。
本文件不是 commit。

**PASS。33=33。差集为空。真实 add/commit/push 未执行。不关闭 Full/G0–G6。**
