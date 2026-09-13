# ds-replay-bounds-20260913-01 收据

- 工作类别：new-development；cwd `C:/Users/PC/Documents/odid编译/wksim`；分支 `main`；HEAD `9e8ba03e43627918d5fab28aa59765a02fb068d1`
- 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 检查退出码 `0`；开工时工作树已含他席修改，本次未触碰（含 perf 目录）
- module/interface：`Simulator/wksim_runtime/replay.py` 的 `load_evidence` 离线证据读取与大小拒绝；直接依赖仅 Python stdlib 与 `wksim_runtime.config._unique_object`

## 问题与修改

原实现先 `path.stat().st_size > MAX_BYTES` 再 `path.read_bytes()`：读取本身无界，文件在 TOCTOU 窗口内增长或被替换时 64 MiB 承诺被绕过（先整文件入内存再做事后长度检查）；验证用的“Evidence changed while reading”重读同样无界。

现改为 `_read_bounded(path, limit)`：真实读取最多请求 `limit + 1` 字节，超过 `limit` 一律拒绝，不缓冲超限记录；被接受的记录必为读到 EOF 的完整内容，绝不静默截断。`stat` 只作快速预拒绝。`files[name]` 的 bytes/sha256 与每条记录的 `raw_sha256` 都绑定实际消费字节。重读同样有界：超限即判为“变了”，不作为证据。

保留：符号链接越界拒绝、`missing_file`/`invalid_result`/`malformed_record`/`unterminated_last_line`/`nonfinite_values`/`identity_mismatch`/`unknown_run_identity`/`source_time_regression`/`sequence_discontinuity` 诊断、原始 JSON 文本与流内行序、physics/fc_boot/ros/unknown 时钟域分离，以及 `reader_status`/`mode`/`order` 语义。

## 交付与哈希

| 文件 | 状态 | sha256 | git blob |
| --- | --- | --- | --- |
| `Simulator/wksim_runtime/replay.py` | 已修改，未暂存/提交 | `4406b7f4e67606c869d5f5aea514e7b89ed1f616c4d00ea4bed4815a23e4f8e2` | `eef3978d` (父 `fd2212a4`) |
| `validation/test_replay_read_limits.py` | 新增，未跟踪 | `f7c5c2f62cb1bf2f77e06dea2a37682cdfa942133d921889d6971ca2c2c219ac` | `c2abd4ef` |

## 真实测试结果（纯 Python、离线）

- 新文件：`16 passed, 1 skipped`
- 受影响套件（新文件 + `test_wksim_replay.py` + `test_wksim_console_records.py` + `test_wksim_console_workspace.py`）：`57 passed, 1 skipped, 84 subtests passed`，原件 `pytest-affected-output.txt`
- 修复前同一套测试为 `8 failed`（未使用有界读取接口、用了无界 `read_bytes`、超限文件被无界读入），修复后转绿
- 可复现红证据 `reproduce_prefix_race.py`（同一探针对比 HEAD 冻结源与交付源）：limit 64 字节、记录 1,048,604 字节时，修复前无界拉取 `[1048604]` 字节，修复后 `[]` 并以“grew or was replaced”拒绝

## 未验证边界

- 本机无符号链接权限（WinError 1314），真实符号链接用例跳过；越界拒绝分支仅由 `Path.resolve` 替身覆盖
- 未读取真实 64 MiB 记录：断言 `MAX_BYTES` 仍为 `64 * 1024 * 1024`，用小上限验证上限行为，满规格路径属“构造有界”而非实测
- 竞态由“stat 过期 + 真实文件”和 reader 替身复现，未用同进程真实并发写者
- 未实测大记录峰值内存；接受路径上界为 `MAX_BYTES + 1`，多块读取时并接副本瞬时可到 `2 * (limit + 1)`
- 仅 Windows 检出；WSL/POSIX 未跑；未重跑更广验证套件与 UI 交互

## 遗留义务

未 `git add`/提交/推送，未发评论或关票，未运行 native/构建/SITL/ROS/UE/MATLAB/厂商模型，未改 `/root/wksim-release-acceptance-fe3` 与历史工作区。G4 完整日志义务仍开放，需父级验收；本收据不构成任何旧 PASS 的延续。
