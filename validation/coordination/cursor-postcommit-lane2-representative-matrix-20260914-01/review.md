# Lane 2 review — Windows + Ubuntu 代表矩阵 + empty-HEAD 祖先语义

plan: `cursor-postcommit-three-lane-verification-plan-20260914-01`  
output: `validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01/`  
date: 2026-09-14  
verdict: **FAIL**

本卡片不授权 add/commit/push，不关闭 issue/gate。未跑 budget 153、G3 179/53/721、frame 45、Full 81、#83、`test_cited_sources_exist`、G1/G5 isolation plugin、native/model/MATLAB/ROS/DDS/SITL/FC/UE/build/flight。4/30/12/5 不是 53/153/179/721/45/81，也不是飞行验收。

## 派发核验

```text
工作类别：historical-comparison / post-commit representative verification（非新开发）
实际 cwd / 分支 / HEAD：
  主仓 C:/Users/PC/Documents/odid编译/wksim  main  59d8da51b4c31b6aa050929ebbe81ccc357acfb5
  WIN  C:/Users/PC/Documents/odid编译/wksim-lane2-win-20260914-01
  UBU  /root/wksim-lane2-ubu-20260914-01
架构祖先检查退出码：0（f333316e6efa6b299b4288a9d91fb2bccedfb9d6 是 HEAD 祖先）
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md
本次 module / interface：无产品源码改动
独占文件：本目录 review.md / review.json 与 windows/ ubuntu/ 日志
不在范围：Lane 1 six-commit diff-tree；Lane 3 SHA256SUMS/secrets；主仓 empty-commit / push
```

## Bindings

| pin | value |
| --- | --- |
| FINAL_HEAD / origin main | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| SOURCE_HEAD | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| ARCHITECTURE_ANCESTOR | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` |
| head_equals_source | false（两机 `rev-parse HEAD` 均 ≠ SOURCE_HEAD） |
| SOURCE / ARCH ancestor | 两机均为 0 |
| WIN_PY | `D:\date\miniconda\python.exe`  3.13.11 |
| UBU_PY | `/usr/bin/python3`  3.10.12 |

两机均按卡片 `git clone --no-tags --single-branch --branch main` 从 `https://github.com/unununnnn/wksim.git` 独立检出，未复用 Lane 1/3 树。Windows 首次 origin clone 绑定成功。Ubuntu 首次 origin clone 到 `/tmp/wksim-lane2-ubu-20260914-01` 同样绑定成功（HEAD=`59d8da51…`，两祖先退出码 0），随后 WSL `/tmp` 被回收；第二次 Ubuntu 检出写到持久路径 `/root/wksim-lane2-ubu-20260914-01`，仍用 origin URL，并以本 lane 自己的 Windows clone 作 `--reference --dissociate`（不是 Lane 1/3）。

## Pass A — FINAL_HEAD 代表矩阵

cwd = 各 clone 根。unittest only，无 isolation plugin。

| host | G1/G5 | G3 | budget | frame | Full |
| --- | --- | --- | --- | --- | --- |
| Ubuntu 3.10.12 | Ran 4 OK 0.158s | Ran 4 OK 0.112s | Ran 30 OK 1.681s | Ran 12 OK 2.772s | Ran 5 OK 0.058s |
| Windows 3.13.11 | Ran 4 **FAILED failures=2** 0.623s | Ran 4 OK 0.285s | Ran 30 **FAILED failures=4** 11.37s | Ran 12 OK 57.439s | Ran 5 OK 0.217s |

Ubuntu 满足 PASS A（4 / 4 / 30 / 12 / 5，failures=0，errors=0）。Windows 不满足。

### Windows 红节点（精确 blocker）

1. `validation.test_g1_g5_offline_drift.HeadIdentityTests.test_head_and_row_blobs_fail_closed_on_drift`  
   `worktree blob SHA-1 drifted: Simulator/wksim_runtime/independent-profile-evidence.json`
2. `validation.test_g1_g5_offline_drift.IndependentEvidenceTests.test_evidence_descriptor_schema_and_local_pin_bytes`  
   pin `audit`：worktree sha256 `7ffbdd39096cec0c4f7e837a7fd0b20814c90a1dd846d9e2e1f00275fb93c6b1` ≠ 记录 `b1df8a365ff9864d02fb8d7508cf2e002b4c87307ee61d0646923ba34eb68b9a`
3. `validation.test_e0_budget_approval_provenance.FrozenInputTests.test_ledger_head_blob_matches_worktree_when_tracked`  
   worktree sha256 `ea3e55fbebf948f02e5a59e64cafe01991756e4fb54cc8ea4225aa04348d8618` ≠ HEAD/package `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d`
4. `LedgerContractTests.test_deliverables_are_lf_normalized` ×3：  
   `e0-budget-approval-provenance-20260914.json`、`59-e0-budget-approval-provenance-20260914.md`、`test_e0_budget_approval_provenance.py` 的 worktree 字节含 `b'\r'`

诊断（Windows clone，`core.autocrlf=true`，未设 local）：`independent-profile-evidence.json` 的 `git show HEAD:` 无 CR、45994 bytes、sha256 `a0f1d60b4ad5b01fb38e775f42907b2b2f1cdc3741da152b3ea81343b7015535`；worktree `read_bytes()` 有 CR、46287 bytes（+293）、sha256 `726898b3536d1267531b4e8995805613a4fba4a16b953116cced876f7107c727`。`git hash-object` 仍等于 HEAD blob（clean filter 把 CRLF 收成 LF），所以 `git status` 干净，但这些节点按 worktree 原字节 fail-closed。这是 Windows 检出 EOL 与测试读盘约定冲突，不是 origin `main` 的 HEAD blob 内容漂移。Ubuntu 同树同 HEAD 全绿。

## Pass B — empty-HEAD 祖先

仅 disposable clone；`--allow-empty`；未 push。两机 `TREE_AFTER == TREE_BEFORE == 5d1cbb9e0ca663d0f10f60d6b645b97b5998b256`；两祖先检查仍为 0；`EMPTY_HEAD != FINAL_HEAD`。

| host | EMPTY_HEAD | tests |
| --- | --- | --- |
| Ubuntu | `83b53d7a005598b62225a4722d3c2f0d28404cbf` | Ran 12 OK 0.555s |
| Windows | `b59660cf745e2015d949e1f94a713850aa33930f` | Ran 12 **FAILED failures=2** 6.434s |

Windows Pass B 红节点仍是上面 G1/G5 两条（empty commit 不改 tree，worktree CRLF 仍在）。其余 10 个 B 节点绿，包括 budget 祖先 pin、frame ancestor、Full JSON identity。

empty-HEAD 身份语义（两机 JSON 一致；Windows 在 empty commit 前于 FINAL_HEAD 读盘）：

- `rev-parse HEAD` ≠ `SOURCE_HEAD`
- budget `observed_at.head` 仍是 capture pin `6eafdf9c0b734db07a9fe790c86b409d3468c10b`
- frame `observed_at.head` 是祖先 pin `521b5124949ea8bb057459142e09b270ae54dde3`，不是当前 HEAD
- Full ledger JSON `head` 是 `6eafdf9c0b734db07a9fe790c86b409d3468c10b`，不是 `rev-parse HEAD`

主仓仍为 `59d8da51…` / `main`，没有 empty-commit，没有 push。两 disposable clone 仅本地 `ahead 1`。

## 未做 / 禁止项

- 主仓 add/commit/push；关 issue/gate
- leftover 脚本未写入本仓库（runner 只在 `%TEMP%` / WSL `/tmp`）
- 未宣称 4/30/12/5 = 全量套件或飞行验收
- 未跑 isolation `pytest -p stdlib_identity_plugin`

## 日志

- `windows/*.log`、`windows/bind.txt`、`windows/empty-head.txt`
- `ubuntu/*.log`、`ubuntu/bind.txt`、`ubuntu/empty-head.txt`

## Verdict

**FAIL**

精确 blockers：

1. Windows Pass A G1/G5 2 red（上列 1–2）。
2. Windows Pass A budget 4 red（上列 3–4）。
3. Windows Pass B G1/G5 2 red（与 1 同一 worktree CRLF）。

非 blocker：Ubuntu Pass A/B 全绿；empty tree 未变；祖先退出码 0；HEAD blob 仍为 LF；未出现 isolation-in-unittest 红。
