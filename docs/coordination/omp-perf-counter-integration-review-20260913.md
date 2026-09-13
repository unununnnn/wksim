# OMP perf 丢失计数器集成审查（2026-09-13）

- 工作类别：new-development（独立 perf 诊断模块只读复核，无模型/控制/固件/UE 依赖）。
- 检出：`main` @ `9e8ba03e43627918d5fab28aa59765a02fb068d1`；f333316 祖先检查退出码 0（本轮复验）。
- 被审源码 SHA256（与给定值及各 receipt `source_sha256` 逐位一致）：recorder `wksim_perf_stream.c` = `aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2`；consumer `perf_stream_consumer.py` = `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc`（与 final-consumer-check.json 钉值一致）；header `ef1eabf2…` 未变。

## recorder 逐项核对（行号基于 aa807f3b）

1. `read_format = 1<<4` 在 perf_event_open 时设置（c:754），每次 start 新建 fd（c:766），计数器随 kzalloc 归零——不依赖 RESET（上一轮已证 RESET 不回零 lost_samples）。
2. mmap（c:780）先于 ENABLE：无 rb==NULL 不计数窗口；inherit=0（c:757）、无 SET_OUTPUT，单事件单 rb 前提保持。
3. stop 顺序：clock+DISABLE+clock（c:1082-1097）→ **仅 disable_ok 时 read16，EINTR 上限 8 次，短读/失败/不可用均记 CAPTURE_INCOMPLETE，非零同样记错**（c:1099-1116）→ stop_requested→join→统计→写 raw/关 raw→ring/perf/storage 清理→序列化 meta（read_ok=false 时 count 写 `null`，c:1228-1232）→关 meta。读取在 DISABLE 之后、close(fd)（c:1210）之前；read 失败或计数非零 ⇒ error_count>0 ⇒ complete=false ⇒ stop=-1（fail-closed，c:1361）。
4. C 哨兵、checkpoint、drain_confirmed 及结构字段已全部移除（全文 grep 无残留）；copy guards（4096B headroom、storage 有界）、几何精确校验、SCHED_OTHER 读回、join 所有权保留、meta 在清理后序列化（cleanup fault 修过的顺序）原样保留。
5. `losslessness_proven` 仍为 false，理由改为"需独立 raw+计数器验证"——recorder 不自证，裁量权在 consumer，方向保守。

## consumer 逐项核对（行号基于 dee9a3b5）

6. `validate_kernel_loss_counter`（py:147-166）在 validate_metadata 内、collector_errors 与 decode **之前**执行（py:238）——前置拒绝成立：字段缺失/部分缺失、config.read_format 非 int 16、read_ok!=True、read_bytes!=16 或 errno!=0、count 非 [0,2^64-1] 纯 int（bool/float/null/负数/溢出全拒）、count>0 各有独立 reason。
7. 无 kernel 字段的旧捕获：verified=False，默认仅 inspection（输出 `stream_completeness_proven=false`+legacy 理由），`--require-kernel-counter` 时以 `kernel_loss_counter_required` 拒绝（py:497-498）。
8. 验证通过时 `window_completeness` 覆盖整个内层区间 [enable_after, disable_before]，方法标注 `post_disable_kernel_event_loss_counter`（py:502-507）；`stream_completeness_proven=true`——上轮审查给出的升级条件（collector_complete && kernel_lost==0 && 全部结构校验）已按原样实现。哨兵认证与 `window_after_stop_check` 已删除；copy/格式/身份/交替/边界/lifecycle 检查全部保留。
9. docstring（py:15-17）仍是"全 32 字节记录"旧表述且未记计数器规则——上一轮已登记的文档债，本轮仍在。

## 原件独立复跑（纯 Python，钉版 consumer dee9a3b5）

10. normal-demo：raw 256B=8×32B，4 pairs，counter 字段 {ok:true,bytes:16,errno:0,count:0}，meta 无 sentinel 键；consumer exit0，`stream_completeness_proven=true`。raw SHA `553b29e3…` 与 receipt 一致。
11. forced-loss（关键升级证据）：raw SHA `263e7ed2…` 复核一致；独立 walk 得 16383 条**全为 SWITCH、0 条 LOST**——本次内核连 LOST 记录都未发布（纯挂起丢失），上一轮的 LOST-record 机制将完全漏检；计数器 read16=26471，meta 携带 owner 的 capture_incomplete 错误、collector_complete=false、stop=-1；钉版 consumer 复跑 exit3 `kernel_loss_counter_nonzero`，与 final-consumer-check.json 两条钉值（normal exit0 / loss exit3+reason）逐位一致。
12. 17 个反例 ×（-01/-02 两套 fixture）逐一复跑，exit/reason 与两份 consumer-receipt 全部 MATCH（含 required_legacy=exit3、inspect_legacy=exit0、raw_lost_despite_zero=`record_lost_present`——证明 meta 计数为零时 raw 仍是已发布丢失的权威）；84 项 consumer 回归复跑 0 失败；原生 6 编译 + 五类 fault（create/join/ring/policy/cleanup）收据与代码路径一致。
13. 观察（非阻断）：archived `counter-cases/inspect_legacy/result.json` 的 reason 文本是哨兵时代措辞，fixture 生成早于钉版 consumer；其 exit0 声明已用钉版 consumer 独立复验。demo/loss receipt 内 consumer SHA（`eeec1fd0…`）为中间修订，最终行为以 final-consumer-check 钉的 `dee9a3b5…` 为准，一致。

## 结论：条件性接受（无阻断项）

接受"read_format=16 + DISABLE 后 read16 + 非零 fail-closed + consumer 前置拒绝"集成，条件：(a) 保持 pinned 内核前提（linux-msft-wsl-6.6.87.2 双 blob + 本机 probe 验证链），换内核重验计数/读路径；(b) 保持新 fd/mmap 先 ENABLE/inherit=0/无 SET_OUTPUT 不变量，改动须重审计数因果；(c) 登记文档债：header G9 仍写"哨兵定义并验证前 blocked"（哨兵已删）、consumer docstring 未更新；(d) 旧捕获维持 inspection-only，任何依赖完整性的消费方必须加 `--require-kernel-counter`。机制已实证覆盖挂起丢失（26471 vs 0 条 LOST），上一轮对 sentinel 机制的保留意见对本集成不再适用。
