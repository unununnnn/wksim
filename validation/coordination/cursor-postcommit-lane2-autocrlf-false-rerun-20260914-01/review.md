# Lane 2 autocrlf=false 纠正重跑

plan: `cursor-postcommit-three-lane-verification-plan-20260914-01`  
card: `validation/coordination/cursor-postcommit-three-lane-verification-plan-20260914-01/lane2.txt`  
original receipt (unchanged FAIL): `validation/coordination/cursor-postcommit-lane2-representative-matrix-20260914-01`  
output: `validation/coordination/cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01/`  
date: 2026-09-14  
verdict: **PASS**

本卡片不授权 add/commit/push，不关闭 issue/gate。未跑 budget 153、G3 179/53/721、frame 45、Full 81、#83、`test_cited_sources_exist`、G1/G5 isolation plugin、native/model/MATLAB/ROS/DDS/SITL/FC/UE/build/flight。4/30/12/5 不是 53/153/179/721/45/81，也不是飞行验收。原回执仍是 FAIL，本目录不覆盖、不改写那份证据。

## 派发核验

```text
工作类别：historical-comparison / post-commit representative verification / autocrlf-false rerun
实际 cwd / 分支 / HEAD：
  主仓 C:/Users/PC/Documents/odid编译/wksim  main  59d8da51b4c31b6aa050929ebbe81ccc357acfb5
  WIN  C:/Users/PC/Documents/odid编译/wksim-lane2-win-20260914-01
  UBU  /root/wksim-lane2-ubu-20260914-01
架构祖先检查退出码：0（f333316e6efa6b299b4288a9d91fb2bccedfb9d6 是 HEAD 祖先）
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md、lane2.txt、原 review.json
本次 module / interface：无产品源码改动
独占文件：本目录 review.md / review.json / captures / SHA256SUMS
不在范围：主仓 add/commit/push/reset/clean；完整套件；native/build/flight/#83
```

## 原 empty HEAD / tree 与失败原因

隔离 clone 开工时仍停在原回执的 disposable empty-HEAD，tree 未变：

| host | 原 EMPTY_HEAD | 原 TREE | 原 core.autocrlf |
| --- | --- | --- | --- |
| Windows | `b59660cf745e2015d949e1f94a713850aa33930f` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` | `true` |
| Ubuntu | `83b53d7a005598b62225a4722d3c2f0d28404cbf` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` | unset |

原回执 **FAIL** 原因：Windows 系统/生效 `core.autocrlf=true`，工作树候选文件被写成 CRLF；测试读盘字节，HEAD blob 仍是 LF。`git status` 干净。精确红节点见原 `review.json` blockers（G1/G5 2、budget 4、Pass B 同 CRLF 2）。Ubuntu 原 Pass A/B 全绿。本重跑不把原 FAIL 改写成 PASS。

## 纠正与恢复

两隔离 clone 设 `core.autocrlf=false`。强制 `git checkout -f -B main 59d8da51b4c31b6aa050929ebbe81ccc357acfb5`。Windows 仅 checkout 后候选文件仍 CRLF（index 视为干净，未重写）；随后在该 clone 执行 `git rm -r --cached .` 再同样强制 checkout，工作树按 LF 重写。Ubuntu 候选文件本来就是 LF。

恢复后：

- 两机 HEAD = `FINAL_HEAD` `59d8da51b4c31b6aa050929ebbe81ccc357acfb5`
- 两机 `core.autocrlf=false`
- 五份候选文件 worktree == HEAD blob，无 CR（含原先红的 evidence / audit / budget json / budget md / budget py）
- `origin ls-remote refs/heads/main` 三处均为 `59d8da51…`
- SOURCE / ARCHITECTURE 祖先退出码均为 0
- `HEAD != SOURCE_HEAD`

## Bindings

| pin | value |
| --- | --- |
| FINAL_HEAD / origin main | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| SOURCE_HEAD | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| ARCHITECTURE_ANCESTOR | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` |
| head_equals_source | false |
| WIN_PY | `D:\date\miniconda\python.exe`  3.13.11 |
| UBU_PY | `/usr/bin/python3`  3.10.12 |

## Pass A — FINAL_HEAD 代表矩阵

cwd = 各 clone 根。unittest only，无 isolation plugin。

| host | G1/G5 | G3 | budget | frame | Full |
| --- | --- | --- | --- | --- | --- |
| Ubuntu 3.10.12 | Ran 4 OK 0.126s | Ran 4 OK 0.109s | Ran 30 OK 1.655s | Ran 12 OK 2.470s | Ran 5 OK 0.054s |
| Windows 3.13.11 | Ran 4 OK 0.362s | Ran 4 OK 0.176s | Ran 30 OK 10.397s | Ran 12 OK 55.132s | Ran 5 OK 0.174s |

PASS A：两机 4 / 4 / 30 / 12 / 5，failures=0，errors=0。

## Pass B — empty-HEAD 祖先

仅 disposable clone；新的 `--allow-empty`；未 push。tree 仍是 `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256`。两祖先仍为 0。`EMPTY_HEAD != FINAL_HEAD`。

| host | EMPTY_HEAD（本次新） | tests |
| --- | --- | --- |
| Ubuntu | `24800304ec20469cd787f9f64907fb01f1c45caa` | Ran 12 OK 0.456s |
| Windows | `ceb796310c2210ea93736dec7014033d45f2aad6` | Ran 12 OK 4.818s |

身份语义（empty-HEAD 之后）：

- `rev-parse HEAD` ≠ `SOURCE_HEAD`
- budget `observed_at.head` 仍是 capture pin `6eafdf9c0b734db07a9fe790c86b409d3468c10b`
- frame `observed_at.head` 是祖先 pin `521b5124949ea8bb057459142e09b270ae54dde3`，不是当前 HEAD
- Full ledger JSON `head` 是 `6eafdf9c0b734db07a9fe790c86b409d3468c10b`，不是 `rev-parse HEAD`

主仓仍为 `59d8da51…` / `main`，没有 add/commit/push/reset/clean。两 disposable clone 仅本地 `ahead 1`。`origin/main` 仍是 `59d8da51…`。

## 未做 / 禁止项

- 主仓 add/commit/push/reset/clean；关 issue/gate
- leftover 脚本未写入本仓库
- 未宣称 4/30/12/5 = 全量套件或飞行验收
- 未跑 isolation `pytest -p stdlib_identity_plugin`
- 未改写原 FAIL 回执

## 日志

全部在 `captures/`。

## Verdict

**PASS**（本纠正重跑）

原回执保持 **FAIL**，原因仍是当时 Windows `core.autocrlf=true` 的工作树 CRLF。本重跑在隔离 clone 关闭转换并重写工作树后，卡片 Pass A 4/4/30/12/5 与 Pass B 12 全绿。
