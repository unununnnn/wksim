# CodeBuddy 场景前沿合同纳入清单 — 20260914-01

工作类别：manifest ingest。只读核验 + 仅写本目录四个产物；未改任何候选或既有文件。

## 核验环境

- 仓库：`C:/Users/PC/Documents/odid编译/wksim`，分支 `main`，HEAD `5370b2324672c9036d41239cb93e21fc5eb42897`（实测一致）。
- 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：`git merge-base --is-ancestor` 退出码 0。
- 未执行：native / ROS / DDS / SITL / FC / UE / MATLAB / models / builds / flights / 用户进程动作。

## 候选核验（4 个路径，见 exact-paths.txt）

| 路径 | SHA256（实测） | 结论 |
| --- | --- | --- |
| `validation/test_scene_frontier_contract.py` | `3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2` | 与任务下发期望一致；git 未跟踪（`??`），与上游 review.json `tracked:false` 一致 |
| `…/cursor-scene-frontier-contract-independent-review-20260914-01/review.md` | `0534e3b48db22498dc973e95bb33416c1600d24e8698585d99f36055dc02a3b2` | 与其 SHA256SUMS 记录一致 |
| `…/cursor-scene-frontier-contract-independent-review-20260914-01/review.json` | `8c72cb9871ed412ff1b1cac0ab00acbcdd6516ea64784a4a5c4ac4e84c9f32bd` | 与其 SHA256SUMS 记录一致 |
| `…/cursor-scene-frontier-contract-independent-review-20260914-01/SHA256SUMS` | `bb78d55b29b53b98d12d310a1c43a5349159b609301e4b3a99a0197f6d500ea9` | 该文件本身未被自列（正常）；内容覆盖 review.md / review.json |

## 审查 JSON 严格解析

`review.json` 以 UTF-8 字节读取、`json.loads` 严格解析成功（schema `wksim.independent-review.v1`）：

- verdict：PASS，`p1_count=0`、`p2_count=0`、`p3_count=5`，findings 数组计数一致（0/0/5）。
- `candidate.sha256_observed` = `3f593d8f…` = 任务期望 SHA。
- `admit_next_batch=true`；`issue_29_acceptance=false`；`#9` OPEN；父票 `#29/#79/#80/#81` 均未解锁。

## SHA256SUMS 核验（含路径与 CRLF 处理）

- 路径解释：上游 `SHA256SUMS` 条目为裸文件名，相对其所在目录解析；在目录内执行 `sha256sum -c` 全部 `OK`（review.md、review.json 两行）。按仓库相对路径展开后与实测哈希一致，无需改写任何历史或原文件。
- 行尾：四个候选文件与 `exact-paths.txt` 均为 LF-only（无 CRLF），哈希为磁盘原始字节，重算一致；不存在 CRLF 归一化歧义。

## 测试运行（仅此项）

```text
python -B -m unittest validation.test_scene_frontier_contract -v
Ran 6 tests in 0.002s
OK
```

6 ran / 6 passed / 0 failed / 0 skipped。运行后复测候选 SHA256 仍为 `3f593d8f…`，未被运行改变。

## 结论

四个候选路径全部核验通过，独立审查 PASS（0 P1 / 0 P2 / 5 P3）。**建议：PASS，可纳入下一批（仅 `validation/test_scene_frontier_contract.py` 单文件，保持该 SHA）。** 本 PASS 不等于 #29 AC、物理消费、真实 UE、Full 或 Goal 通过。

## 限制（继承上游审查 limits）

- `#9` OPEN（ABI 证据阻塞仍在）。
- `#29` OPEN，原 AC 未勾；子票 `#79/#80/#81` 已 CLOSED 但不因本 PASS 解锁父票。
- 未证明物理接触力/坡度/侧碰、真实 UE 同置、FC/SITL/ROS 闭环、显示断开。
- 本清单不执行 `git add`/纳入动作。
