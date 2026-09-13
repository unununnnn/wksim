# ds-replay-bounds-20260913-01 第 2 轮：短读单缓冲

- 工作类别：new-development；分支 `main`；HEAD `9e8ba03e43627918d5fab28aa59765a02fb068d1`
- 派发写的 cwd `…/wksim/main` 不存在；实际 cwd 为项目根 `C:/Users/PC/Documents/odid编译/wksim`（即根 + 分支 main），已按此核验
- 祖先 `f333316e…` 退出码 `0`；施工前确认 AGENTS/实施报告/接续合同/交付策略四文件相对 HEAD 未修改，且本轮审查对象正是第 1 轮交付哈希（`4406b7f4…` / `f7c5c2f6…`）
- module 不变：`Simulator/wksim_runtime/replay.py` 离线证据读取；依赖仍为 stdlib + `config._unique_object`；无 native/模型/网络/构建

## 接受的问题与修法

第 1 轮 `_read_bounded` 用 chunk 列表 + join 累积。短读很多时，保留的 bytes 对象与列表指针开销随**读取次数**增长，而非随 limit 增长，因此“峰值 ≤ 2*(limit+1)”当时并不成立（记录字节上限本身未被突破）。第 1 轮收据里的峰值说法由本轮取代；第 1 轮文件保留为历史，未改写。

现改为单个有界 `bytearray` 累积：

```python
cap = limit + 1
buffer = bytearray()
while len(buffer) < cap:
    remaining = cap - len(buffer)
    chunk = handle.read(remaining)
    if not chunk:
        break
    if len(chunk) > remaining:
        return None            # 立即拒绝，不存该 chunk
    buffer += chunk
return None if len(buffer) > limit else bytes(buffer)
```

- 总请求字节仍 ≤ `limit + 1`；EOF 完整读语义保留；接受即完整记录，绝不静默截断
- `len(chunk) > remaining` 时不 append、不 join，直接拒绝
- hash/行序/时钟域/“Evidence changed while reading”变化拒绝语义不变

## 实测（不是公式声称）

`reproduce_short_read_memory.py`：64 KiB 记录、每读 1 字节（65537 次读）、reader 关闭请求记录以免double 自身主导；对两个版本跑同一探针，tracemalloc 取峰值。

| 版本 | 接受 | 记录完整（hash 一致） | 峰值 traced | 相对 limit |
| --- | --- | --- | --- | --- |
| 第 1 轮列表 + join（冻结 `replay-list-join-20260913-01.py`） | 是 | 是 | 5,871,057 B | 89.585× |
| 本轮单 bytearray | 是 | 是 | 131,986 B | 2.014× |

探针退出码 `0`。这是 CPython 3.13.11 / Windows 上一种合成 1 字节短读分布的**实测**，只含 Python 追踪分配，不含未追踪的解释器/OS 开销；不据此声称任何通用精确峰值，也不声称其他块大小或更大 limit 的峰值。

结构性说明（未测）：常驻内容为单个 bytearray，上限 `limit + 1`；接受后另有一次 ≤ `limit` 的不可变 bytes 拷贝；不按读取次数保留对象。bytearray 的扩容余量依解释器实现，未做断言。

## 测试

新增 4 项：小上限逐字节短读（请求大小从 `limit+1` 递减、hash 绑定完整记录）、流中段 oversized chunk 立即拒绝且不再继续读、单缓冲结构守卫（无 chunk 列表 append/join）、64 KiB 逐字节读的实测峰值 < `4 × limit`。

- 本文件：`20 passed, 1 skipped`
- 受影响套件（本文件 + `test_wksim_replay.py` + 两个 console 测试）：`61 passed, 1 skipped, 84 subtests passed`，原件 `pytest-affected-output-round2.txt`
- 第 1 轮竞态探针重跑仍退出 `0`（冻结 HEAD 源仍显示无界读，交付源无界读为 `[]` 并以 “grew or was replaced” 拒绝）

## 交付

| 文件 | 状态 | sha256 | git blob |
| --- | --- | --- | --- |
| `Simulator/wksim_runtime/replay.py` | 已修改，未暂存/提交 | `593f32b1b4c55a3aef53f0ba32bc889002e0a4516d05a020882732251876ffdc` | `1e00b0f0`（相对 HEAD +48/−4） |
| `validation/test_replay_read_limits.py` | 新增，未跟踪 | `9a75a3f0a53c75b15bf01df743981bc86171c8535711af045022896e679d546c` | `d37087fe` |

## 未验证边界

- 实测仅覆盖 64 KiB / 每读 1 字节 / Windows / CPython 3.13.11；其他分布、更大 limit、POSIX 未测
- tracemalloc 只追踪 Python 分配，不是 OS RSS；bytearray 扩容余量未断言
- 真实带缓冲文件对象不会短读（regular file 一次返回到请求量），逐字节场景只由 reader 替身产生
- 未读真实 64 MiB 记录；仅断言 `MAX_BYTES` 仍为 `64 * 1024 * 1024`
- 符号链接真实用例在本机仍跳过（WinError 1314），该分支仅由 `Path.resolve` 替身覆盖
- 未做同进程并发写者测试；竞态仍用 stat 过期 + 真实文件与 reader 替身复现
- 未重跑更广验证套件与 UI 交互

## 遗留义务

未 `git add`/提交/推送，未发评论关票，未动他席文件与 perf 目录，未改 `/root/wksim-release-acceptance-fe3` 及历史工作区；未运行 native/构建/SITL/ROS/UE/MATLAB/厂商模型。未扩成新框架，改动限于原两个文件。G4 完整日志义务仍开放，需父级验收。
