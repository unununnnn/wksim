# 参考端 pqr 输入观测模式独立审查（2026-09-13)

历史审查版本：probe SHA 7ab693c4ce8532671dc89d1e1aea9b8edc66d7c089474ae1ae0c8937470d0e37。主会话后续加入实际连接追踪并完成 run-04/05，见 [实际求解边界](../2026-09-13-first-step-solve-boundary.md)。下文静态测试是当时的字符串检查，已保留为 validation/coordination/g6-reference-probe-20260913/execution-04/reviewer-static-tests.py.txt；不作为当前实现的测试或运行证明。

审查对象：OMP 在 `tools/probe_reference_first_step.m` 的新增 `probe_pqr_input` 模式（默认关闭）。
核验依据：实际源码 + **本机 MATLAB 文档**(`D:\matlab\install date\help\...`)，不运行 MATLAB/模型/ROS/飞控/构建，不嵌套、不操作 Git。修复后由 `validation/test_probe_reference_first_step_static.py`(10 项静态契约）锁定。

## 发现并修复的问题

| # | 问题 | 位置 | 本机文档证据 | 修复 |
| --- | --- | --- | --- | --- |
| 1 | `~ishandle(src_block)` 误拒合法块句柄 | 原 ~163 行 | `matlab/ref/ishandle.html`:`ishandle` 仅"valid **graphics or Java** object handle";Simulink 数值块句柄非图形/Java → 恒 false | 去掉 ishandle；用文档哨兵 `src_block == -1`（无源）+ `get_param(src_block,'BlockType')` 探针（非法即抛错→置空）校验 |
| 2 | `numel(rto.InputPort)` 枚举端口错误 | 原 `local_capture_pqr` | `simulink/slref/simulink.runtimeblock.html`:`InputPort`/`OutputPort` 是**方法**，端口数是属性 `NumInputPorts`/`NumOutputPorts`;`numel` 方法句柄恒为 1 | 改用 `rto.NumInputPorts`，逐端口 `rto.InputPort(i)` |
| 3 | 仅捕获 `OutputPort(1)` | 原 `local_capture_pqr` | 同上：`NumOutputPorts` 为实际输出端口数 | 逐端口枚举**全部**实际输出（`rec.outputs`,1..NumOutputPorts) |
| 4 | `opts.probe_pqr_input` 无标量 logical 校验 | 默认块 | —（健壮性） | 新增 `islogical && isscalar` 校验，否则报错 |
| 5 | `is_product_block = strcmp(BlockType,'Product')` 把类型当身份 | 原 ~186 行 | —（逻辑） | 移除该身份标志；BlockType/参数如实记录，注明 Product 类型≠求解器 Product2/mrdivide |
| 6 | "3 numerator inputs" 把元素数说成端口数 | note 字段 | —（术语） | 改为"3 元分子向量 + 9 元（3x3）惯性矩阵 + 3 元结果向量"是**元素数**参考，非端口数 |
| 7 | 文档暗示实际矩阵=参数 | 说明文 | — | 明确以运行时读数为准，不假设等于 `ModelParam_uavJ` |
| 8 | 文档"默认路径零执行变化/字段完全相同"与源码矛盾 | `reference-pqr-input-probe-20260913.md` | 源码：无条件 `report.pqr_input_probe=...` + 预留 3 个 workspace 名 | 改成真实有限承诺：默认路径执行/采集一致，但报告新增 `pqr_input_probe` 节、预留并清理 3 个 workspace 名 |

## 逐项核对未动的保留不变量

- 三哈希钉（输入 CSV `721c88bf…`、模型 SLX `c232e2e9…`、init `9ca09a95…`)、R2022b 版本断言：保留。
- Java 输出 `CREATE_NEW`（绑定拒绝+打开于一次文件操作）、原子新目录预留：保留。
- UDD.Data 探测（`local_native` 对运行时数据对象直读 `.Data`，失败记原因+可枚举属性）：保留。
- cache/codegen 隔离 + 环境恢复 onCleanup、StartFcn/InitFcn 读-链-恢复、listener 清理、`close_system(model,0)` 不保存：保留。
- workspace 清理覆盖新模式变量（`wk_probe_log2`/`wk_probe_dropped2`/`wk_probe_pqr_target`)：保留。
- 未改 SLX、未改旧 report(run-01/02/03 原件不动）。

## 内部核验（纯静态/无 MATLAB)

`python -m pytest validation/test_probe_reference_first_step_static.py` → **10 项通过**：
ishandle 不在代码、-1 哨兵+get_param 校验、NumInputPorts/NumOutputPorts 使用、
pqr 捕获枚举全部输出端口、opts 标量 logical 校验、默认关闭、无 product 身份标志、
哈希钉保留、CREATE_NEW+回调恢复、workspace 清理覆盖、文件函数/括号平衡。

## 主会话需实跑的精确检查（本审查未运行）

1. **ishandle 修复有效性**：开启 `opts.probe_pqr_input=true` 实跑，确认 p,q,r 积分器上游块**不再被误拒**为"no resolved source block"，而是解析出真实 `BlockType`/路径（或如实 virtual-routing/unavailable)。
2. **端口计数正确性**:pqr 上游块报告里 `input_port_count`/`output_port_count` 等于该块真实端口数（经 `NumInputPorts`/`NumOutputPorts`)，`inputs`/`outputs` 逐端口全精度 hex 非恒 1 端口。
3. **全输出捕获**：若上游块为多输出，`outputs` 含全部端口；单输出则 `outputs` 恰 1 元素。
4. **默认关闭回归**:`opts` 缺省/`probe_pqr_input=false` 实跑，确认 major 输出与四积分器 verified 模式逐位一致，报告仅多 `pqr_input_probe`(enabled=false) 节。
5. **事件序**:pqr 上游 PostOutputs 的 `order` 为真实回调序；与四积分器 stage 事件按文件序对应（不按相同时间合并）。
6. **恢复保护**：实跑后模型 StartFcn/InitFcn 恢复原值、path/fileGenControl 恢复、模型 close(0) 未保存、无残留 listener/workspace 变量。

## 边界

仅静态审查 + 纯测试；未运行 MATLAB/模型/ROS/飞控/构建；不嵌套、不操作 Git;SLX 与旧 report 未动；R1/G6 状态不变。以上为源码审查结论，实跑验证归主会话。
