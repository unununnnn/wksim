# G1/G5 最终私有 index 精确暂存审计 — 独立收口

2026-09-14。只读复核
`validation/coordination/cursor-g1-g5-final-private-stage-audit-20260914-01/**`
与当前 git 状态。候选、历史回执、真实 git index / refs 未作为写入目标。
**未运行测试。未改候选。未改历史回执。未 `git add` / commit / reset / update-ref。**
写入仅在
`validation/coordination/cursor-g1-g5-final-private-stage-finalize-20260914-01/**`。

**裁决：PASS。** 0 P1；0 P2；其余为 P3。

这不是 owner 批准，也不关闭 #39 / G1 / G5 / Full。这不是一次主仓 add / commit。

## 派发

```text
工作类别：独立收口 / private-index exact-stage audit closeout
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-g1-g5-final-private-stage-audit-20260914-01 最终文件与当前 git 状态
module / interface：无产品代码变更
独占写入：validation/coordination/cursor-g1-g5-final-private-stage-finalize-20260914-01/**
依赖（只读）：上述审计目录；validation/test_g1_g5_offline_drift.py；
             四枚 force-add 依赖；22 条 exact paths 现磁盘字节
验证：JSON 可解析；SHA256SUMS 真实换行并与磁盘重算一致；
      候选 SHA-256 独立重算；22 路径完整无重复；
      私有 index diff 与预期集合一致；真实 index 内容 / refs 对照审计钉；
      _*.py / _rehearsal.json / scratch 不在暂存清单
范围外：改候选或历史回执、真实主仓 add/commit/stage/reset/clean、
        重跑私有 index 演练、重跑聚焦套件 / #83 / native / model /
        MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。收口在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

开工时执行过一次 `git update-index --refresh`（只刷新 stat；两处已跟踪脏文件报 `needs update`）。`.git/index` 内容 SHA-256 与字节仍等于审计钉 `de15d624…` / 1555140；文件 mtime 新于审计记录。本收口未再写入 index，也未 `git add`。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 审计最终文件可解析 | **PASS** | `review.json` / `private-index-diff.json` / `hash-verification.json` 均 `json.loads` 成功；`review.md` 12535 字节可读 |
| SHA256SUMS 真实换行且命中磁盘 | **PASS** | 520 字节；6 个 `0x0A`；0 CR；0 字面 `\\n`；6/6 重算命中 |
| 候选哈希 = 预期钉 | **PASS** | 独立重算 `83234a89fa62be49931dc1adee7d36e8a7780d9f8f781b854f69214d388a12c5`；42074 字节；CRLF 917 |
| 22 条 exact paths 完整无重复 | **PASS** | staged / expected / name-status / staged_rows 均为 22 unique 且集合相等；extra=[]、missing=[] |
| 私有 index diff 与预期一致 | **PASS** | 全部 `A` / `100644`；1 ordinary + 21 force-add；树 `c92912eb…`；parent=HEAD；四依赖哈希仍钉 |
| 真实 index 内容 / refs 未变 | **PASS** | index SHA-256 `de15d624…`、1555140 字节与审计前后钉相同；`refs/heads/main`=HEAD `6eafdf9c…`；`diff --cached` 空 |
| 临时文件不进暂存清单 | **PASS** | `_fix_sums.py` / `_finalize.py` / `_rehearse.py` / `_rehearsal.json` 在审计目录但不在 22 路径；`scratch/` 不存在 |
| 本审查总体 | **PASS** | 0 P1 / 0 P2 |

## 审计最终文件

审计目录正式七件（`this_audit_files`）均可读。SHA256SUMS 只列其中六件正文，不含自身，也不含 `_*.py` / `_rehearsal.json`。

| 文件 | 字节 | SHA-256（独立重算 = SUMS） |
| --- | ---: | --- |
| `review.md` | 12535 | `c2de2631…a88e087e` |
| `review.json` | 5406 | `dabd9b5a…79459a3b` |
| `exact-stage-commands.txt` | 5953 | `d4a4cd58…f1ec7c90` |
| `durable-evidence-manifest.txt` | 9510 | `b3730c3d…7e5ee8a5` |
| `private-index-diff.json` | 56866 | `ffee2750…19abd732` |
| `hash-verification.json` | 32237 | `22dbf843…33665627` |
| `SHA256SUMS` | 520 | 自身不列；原始字节含 6 条真实 LF |

`review.json` 裁决 `PASS`，`staged_path_count=22`，`candidate_edited/receipts_edited/git_mutated/tests_rerun` 均为 false，与 `review.md` 一致。

## 22 条 exact paths

来源：审计 `expected_paths`。与 `staged_paths` / `name_status` / `staged_rows` 集合相同。全文见 `exact-paths.txt`。

- 普通 add（1）：`validation/test_g1_g5_offline_drift.py`
- force-add 依赖（4）：两枚 promotion-flight JSON + `stdlib_identity_plugin.py` + `isolation_after_g1g5.py`
- force-add 证据（17）：repair `review.md` / `review.json` / `before-failure.json` / `minimal-commit-manifest.txt` / `SHA256SUMS` + 两端信封/empty 计数 + 四序列 JSON + 两份 Linux commit-sequence

命令文件：`git add --` 22 次（仅候选入库），`git add -f --` 21 次；`{force} ∪ {候选}` = 预期 22 集。

## 绝不进入暂存清单

| 路径 | 审计目录现状 | 在 22 条 exact paths |
| --- | --- | --- |
| `_fix_sums.py` | 存在，1507 字节 | 否 |
| `_finalize.py` | 存在，17054 字节 | 否 |
| `_rehearse.py` | 存在，22807 字节 | 否 |
| `_rehearsal.json` | 存在，80511 字节 | 否 |
| `scratch/` | 不存在 | 否 |

`this_audit_files` 与 SHA256SUMS 也不含上述临时文件。本收口目录不复制它们，也不留临时脚本。

## 真实 index / ref guard

对照审计 `private-index-diff.json` 的前后钉。详见 `index-ref-guard.json`。

| 项 | 审计记录 | 本收口观察 | 内容是否相同 |
| --- | --- | --- | --- |
| HEAD / `refs/heads/main` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` | 相同 | 是 |
| HEAD tree | `435471df1371a0bec80d4b6013c3bc9cbc8af938` | 相同 | 是 |
| `.git/index` SHA-256 | `de15d624f0417e89a1a534f947b0fc3e0c33aa69a6db99ab694e5c4f1a9c7c7a` | 相同 | 是 |
| `.git/index` 字节 | 1555140 | 1555140 | 是 |
| `.git/index` mtime | 1789336340.6591258 | 1789336902.7088904 | 否（仅文件 mtime） |
| `diff --cached` | 空 | 空 | 是 |
| 脏已跟踪仍停在 HEAD blob | `382f2c17…` / `0688c231…` | index 仍是这两枚；工作树 `dc0a843a…` / `cc7c4dcb…` | 是 |

## 发现（P1–P3）

| id | 级 | 标题 |
| --- | --- | --- |
| — | P1 | **无** |
| — | P2 | **无** |
| P3-FINAL-REVIEW-PENDING-APPEND | P3 | final-review 仍缺 `review.md` / `review.json` / `SHA256SUMS`；待追加，不猜、不入库。 |
| P3-REPAIR-SUMS-HAS-UNSELECTED | P3 | 原 repair SHA256SUMS 仍列 61 个未选文件。不得对原 SUMS 做选中集 `-c`。 |
| P3-AUDIT-TEMP-LEFTOVERS-NOT-STAGED | P3 | 审计目录留有 `_*.py` 与 `_rehearsal.json`；它们不在 22 条暂存清单，本收口不复制。 |
| P3-INDEX-MTIME-ADVANCED-CONTENT-PIN-HELD | P3 | 本会话 `.git/index` 文件 mtime 新于审计记录；内容 SHA-256 / 字节 / refs / cached-empty 仍钉。 |
| P3-SUMS-OMITS-SELF | P3 | 审计与本收口 SHA256SUMS 均不列自身。 |
| P3-EVIDENCE-FORCEADD | P3 | 四依赖与 17 证据被 `/validation/*/` 忽略，须精确 `git add -f`。 |
| P3-UNRELATED-DIRTY | P3 | 两处已跟踪脏文件必须保持在 HEAD blob。 |
| P3-TEMP-COMMIT-TREE-NOT-A-REF | P3 | 审计 `commit-tree` `99737d52…` 只核父子/tree，不是主仓提交。 |

无发现构成候选相对钉 `83234a89…a12c5` 漂移，也没有临时文件进入 22 条 exact paths。

## 非声称

不关闭 #39 / G1 / G5 / Full，不批准 owner 项，不改判既有 PASS/FAIL，不声称 final-review 已完成。未重跑任何套件、#83 或私有 index 演练。未做 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行。主仓无 `git add` / commit / stage / reset / clean。本文件不是 commit。
