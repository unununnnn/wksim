# Lane 2 代表矩阵（快速双系统影子 v2）

2026-09-14。执行卡片 A 的 4/4/30/12/5 与 B 的 12 个 empty-HEAD 节点。
用户绑定 FINAL_HEAD=`59d8da51b4c31b6aa050929ebbe81ccc357acfb5`。
测试 clone 是本地共享对象（`git clone --shared` + 非浅 facade），**不是**直接 origin clone。
写入仅在 `validation/coordination/cursor-postcommit-lane2-representative-matrix-fast2-20260914-01/{review.md,review.json,SHA256SUMS,captures/**}`。
未改主仓候选或原 lane2。未 add / commit / push。未跑完整套件 / native / build / flight / #83。

**裁决：PASS。** 两宿主最终代表集均为 Ran 4/4/30/12/5、failures=0、errors=0、rc=0；两宿主 empty-HEAD 后 tree 仍为 FINAL tree，两祖先退出码 0，B 各 Ran 12 OK。
Windows 第一次卡片 A 因系统 `core.autocrlf=true` 检出 CRLF 而红；`core.autocrlf=false` 强制刷新工作树后复跑转绿。Ubuntu 沿用既有 A/B 捕获，未再整仓 clone。
`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。
`4/4/30/12/5` 不等于 53/153/179/721/45/81，也不等于飞行验收。

## 派发

```text
工作类别：postcommit-lane2-representative-matrix-fast2
         （影子核查，非新开发、非新架构验收、非原 lane2 权威目录）
规划仓 cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                         main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
SOURCE 祖先：6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD -> 退出码 0
Win clone：C:/Users/PC/AppData/Local/Temp/wksim-lane2-fast2-win-20260914-01
Ubu clone：/root/wksim-lane2-fast2-ubu-20260914-01
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、lane2.txt
module / interface：无产品代码变更
独占写入：本目录 review.md、review.json、SHA256SUMS、captures/
范围外：原 lane2 目录；主仓 add/commit/push；完整 153/179/53/721/45/81；
        native / 构建 / 飞行 / #83；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本核查在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## Clone（本地共享对象，非 origin clone）

规划仓是浅克隆（`.git/shallow` = Prometheus 上游 `5dcd8cfa…`）。对规划仓直接 `git clone --shared` 会被 Git 忽略 `--shared`，走 `upload-pack` / `pack-objects` / `index-pack` 复制整仓；探测已中止，TRACE 见 `captures/win-planner-direct-shared-aborted-trace.txt`。未传 `--no-hardlinks`。

实际测试 clone：

1. 各宿主建非浅 bare facade，`objects/info/alternates` 指向规划仓 objects。
2. `git clone --shared` 从 facade 检出。Win/Ubu 均 `ALTERNATES=yes`，pack 目录空，TRACE 无 `pack-objects` / `index-pack` / `unpack-objects`。
3. 随后 `git remote set-url origin https://github.com/unununnnn/wksim.git`。
4. clone 内 `ls-remote origin refs/heads/main` 与独立 URL `ls-remote` 均为 `59d8da51…`。
5. 两祖先退出码 0；`HEAD != SOURCE_HEAD`。

| 宿主 | clone | facade alternates | clone alternates |
| --- | --- | --- | --- |
| Windows | `%TEMP%/wksim-lane2-fast2-win-20260914-01` | `C:/Users/PC/Documents/odid编译/wksim/.git/objects` | facade `/objects` |
| Ubuntu-22.04 | `/root/wksim-lane2-fast2-ubu-20260914-01` | `/mnt/c/Users/PC/Documents/odid编译/wksim/.git/objects` | facade `/objects` |

**不能声称直接 origin clone。** `from_origin=false`。

## Windows 第一次卡片 A（系统 autocrlf，红）

系统 `D:/install/Git/etc/gitconfig` 的 `core.autocrlf=true` 把 LF blob 检出成 CRLF。工作树相对 HEAD blob 漂移。捕获保留为 `captures/win-A-*-system-autocrlf.txt`。

| 组 | Ran | 结果 |
| --- | --- | --- |
| G1/G5 | 4 | FAILED (failures=2)：worktree blob SHA-1 drifted；pin sha256 不等 |
| G3 | 4 | OK |
| budget | 30 | FAILED (failures=4)：ledger worktree blob；三份 deliverable 含 CR |
| frame | 12 | OK（60.466s） |
| Full | 5 | OK |

这是检出换行，不是候选缺陷。未据此改主仓。

## Windows LF 刷新与复跑（绿）

`git config core.autocrlf false` 与 `core.eol lf` 后，清空工作树（保留 `.git`），再 `git -c core.autocrlf=false -c core.eol=lf checkout --force`。抽样 `independent-profile-evidence.json` / budget ledger / budget 测试 / `59-…md` 均为 `has_cr=false`，见 `captures/win-lf-refresh.txt` 与 `win-lf-refresh-bytes.txt`。

| 组 | Ran | 耗时 | rc |
| --- | --- | --- | --- |
| G1/G5 | 4 | 0.194s | 0 |
| G3 | 4 | 0.013s | 0 |
| budget | 30 | 10.622s | 0 |
| frame | 12 | 53.838s | 0 |
| Full | 5 | 0.065s | 0 |

Python：`D:\date\miniconda\python.exe` 3.13.11。

## Ubuntu 既有 A/B（未再 clone）

Ubuntu-22.04 `/usr/bin/python3` 3.10.12。A/B 捕获已在本目录，本轮只核对，不重复整仓 clone，不重跑。

| 组 | Ran | 耗时 | rc |
| --- | --- | --- | --- |
| G1/G5 | 4 | 0.100s | 0 |
| G3 | 4 | 0.009s | 0 |
| budget | 30 | 13.278s | 0 |
| frame | 12 | 29.897s | 0 |
| Full | 5 | 0.014s | 0 |

## 卡片 B empty-HEAD（可弃用 clone，未 push）

| 宿主 | EMPTY_HEAD | tree 前/后 | 祖先 | B |
| --- | --- | --- | --- | --- |
| Windows | `7e4117ceec85abe052b77bee0bfe2894cf86ded1` | `5d1cbb9e…` / `5d1cbb9e…` | 0 / 0 | Ran 12 in 4.670s OK |
| Ubuntu | `71c7d17aaa240edc33f24a6117ac32e6a554ab91` | `5d1cbb9e…` / `5d1cbb9e…` | 0 / 0 | Ran 12 in 2.493s OK |

`EMPTY_HEAD != FINAL_HEAD`。未 `git push` empty。主仓 HEAD 仍为 `59d8da51…`。

## 禁止项

未跑 budget 153、G3 179/53/721、frame 45、Full 81、`test_cited_sources_exist`、isolation pytest、native / 构建 / 飞行 / #83。
未把 4/4/30/12/5 写成全量或飞行验收。未改原 lane2。未主仓 add/commit/push。

## 输出

`review.md`、`review.json`、`SHA256SUMS`（不列自身）、`captures/`。
