> Main integration supersedes prior uncompiled claims. Final native baseline uses stop(void **handle, ...), explicit caller ownership and cleanup-before-metadata. All fault cases and a normal raw-record decode passed. See ../../../docs/2026-09-13-perf-stream-recorder-admission.md and ../perf-stream-native-acceptance-20260913-05/main-verdict.json. Losslessness, whole-flight overhead and architecture acceptance remain unproven.

# 自线程 switch 流记录器（perf-stream-contract 实现候选）

目录：`validation/coordination/ds-perf-stream-recorder-20260913-01`（唯一写入目录）。
实现对象：`docs/coordination/perf-stream-contract-20260913.md`。**新模块，不改旧能力原件**（`ds-perf-self-capability-20260913-01` 逐字节未动）。未接 runner、未编译、未跑 native/WSL perf、未加 Python 镜像或新框架。

> 本轮（review 后修复）：main 实读发现 5 处阻断（NULL attr 却声称 EXPLICIT_SCHED、栈上 args 跨线程读、两线程共享 error_count 无同步、guard 只比 storage、collector 按 header 解析并丢尾），已按下面"安全性修复"全部改写。哨兵完整性仍未审查：**不得声明已可飞行**。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `wksim_perf_stream.h` | 契约 API：`wksim_perf_start(void**)` / `wksim_perf_stop(void*, raw, meta)`；另加只读的 `wksim_perf_last_error()`（见 G8） |
| `wksim_perf_stream.c` | 实现：自身线程 DUMMY 事件 → 有界 128 MiB 存储 → 独立 reader 线程（显式 SCHED_OTHER + 读回 + ready 握手）→ 原始块搬运 → disable/join/独占写/全量清理 |
| `wksim_perf_stream_demo.c` | 短 demo：传输出目录、4 次 150 ms 短 sleep、拒绝覆盖、事后独立回读校验 |

## 本轮安全性修复（逐条对应 main 的实读结论）

| main 的阻断 | 修复 |
| --- | --- |
| `pthread_create(..., NULL, ...)` 却声称 `PTHREAD_EXPLICIT_SCHED` | 改为真实 `pthread_attr_t`：`pthread_attr_init` + `setinheritsched(PTHREAD_EXPLICIT_SCHED)` + `setschedpolicy(SCHED_OTHER)` + `setschedparam(prio 0)`；**任一步用返回码（不是 errno）判失败即 start 失败**；`pthread_attr_destroy` 在 create 后立刻调用。创建线程不再可能继承 manager 的 FIFO |
| 读栈上 `args.policy_verified`，reader 可能未写、args 可能已出作用域 | 删除栈上 `struct wksim_perf_start_args`；线程参数就是 handle 本身。新增 `ready_lock` + `ready_cond` + `reader_ready` + `reader_policy_ok`，全在 handle 内并在锁下读写；**owner 必须在 RESET/ENABLE 之前等到 ready**，等不到即失败并回收 |
| 主线程 `record_error` 与 reader 共享 `error_count`/数组，data race | 两线程对错误数组的读写全部进 `error_lock` 互斥；计数与槽位在同一次临界区内更新；join 之后调用 `settle_errors()` 把 owner 线程失败**重排到最前**（生命周期失败优先于 collector 失败，组内顺序不变）并刷新线程本地错误串。collector 正常路径不记错误，锁不在热路径 |
| guard 用 `pending+4096 > storage free`，根本没检查 ring 剩余 | 拆成两个独立判据、两个独立计数：**ring 余量** `pending + 4096 > ring_bytes` → `ring_pressure_events`；**storage 余量** `chunk > storage_capacity - captured_bytes` → `storage_pressure_events`。任一触发即记 `pressure_guard` 并停止，不截断、不静默丢 |
| collector 按 header 解析、部分/畸形丢尾，不是 raw 原样搬运 | 删除 `copy_one_record()`。collector **每次只把已发布的 `[data_tail, data_head)` 原始字节块 memcpy 进 storage**（回绕拆两段），随后 release 发布 tail。collector 内不再出现 `perf_event_header`/`record_size`/类型判断；字节零改动、零补齐、零重排，LOST/UNKNOWN/任意类型原样保留 |
| join 失败仍释放可能被 reader 访问的 storage/mmap/handle 并宣称 `reader_running=false` | `join_reader()` 用返回码判断；失败时置 `join_failed=true`、**保持 `reader_running=true`**，`stop` 立即 `return -1`，**不 munmap、不 close、不 free、不写文件**；header 写明调用方保留 handle 所有权且不得重试 stop。join 成功才进入释放路径 |

补充一致性修正：

- metadata 的 `data_offset`/`data_size` 与映射几何**严格相等**，**取消 0 回退**（旧代码在两者皆为 0 时以 `meta_geometry_exact=false` 放行）。现在任一项为 0、非页大小、非 `ring_bytes`、非 2 的幂，均记 `meta_geometry` 并失败；观测值一并写入 metadata 便于事后定位。
- `stop` 不再在"语义失败但无 errno"时返回 `errno=0`：改为 `EIO`。
- 语义类失败（压力/几何）用 `record_errorf` 带上 head/tail/ring/pending/captured 具体数值，便于复现。
- demo 回读由"raw 必须是 32 的整数倍"改为**8 字节对齐**（perf 记录的对齐单位），并新增 `losslessness_proven: false`、`meta_geometry_exact: true`、`reader_joined: true`、`join_failed: false` 四项标记校验。

## 与契约逐条对应

| 契约要求 | 实现 |
| --- | --- |
| `pid=0, cpu=-1, group_fd=-1, CLOEXEC, inherit=0, context_switch=1, sample_id_all=1, TID\|TIME\|CPU, CLOCK_MONOTONIC, exclude_kernel=1` | `attr` 逐项如此（`exclude_kernel=1` 亦符合 OMP 对 paranoid=2 的实证要求）；`exclude_hv=0` |
| enable 前抓 owner PID/TID 与 boot | `getpid`/`SYS_gettid`/`/proc/sys/kernel/random/boot_id` 在读时钟与 ENABLE 之前完成（G1） |
| 独立 native reader、显式 SCHED_OTHER、读回验证 | 属性结构 + reader 内 `pthread_getschedparam` 读回双保险；读回不是 SCHED_OTHER 或优先级非 0 则记 `thread_policy` 且 start 失败；不改主线程/其他线程/亲和性/sysctl/rlimit |
| 有界 128 MiB 存储、enable 前 map 128 数据页、收集循环零分配/解析/IO/回调 | `mmap(MAP_PRIVATE\|MAP_ANONYMOUS)` 128 MiB 并逐页预触；环 = 128 × `sysconf(_SC_PAGESIZE)`，与 `data_offset`/`data_size` 严格交叉校验；循环内只有 `memcpy` + 原子内存序 |
| 10 ms 有界轮询、EINTR、原子停止 | `WKSIM_PERF_POLL_NS`（默认 10 ms，编译期常量，G4）；`nanosleep` 重试并每次复查停止标志；`_Atomic bool stop_requested` |
| 前向可写环、acquire 读 head、校验 head/tail 与容量、回绕先拷贝再 release 发布 tail | `__ATOMIC_ACQUIRE` 读 `data_head`（relaxed 读 `data_tail`），`head-tail > ring_bytes` 立即失败；`ring_copy` 处理回绕；拷贝后 `__ATOMIC_RELEASE` 写 `data_tail` |
| 距环容量 4096 字节内即判无效 | ring 余量判据独立实现并计数（G6） |
| 存储耗尽/任何收集错误 → capture 不完整、不静默截断/增长/覆盖/跳过 | 第一处错误即录音并停止拷贝；`collector_complete` 只在零错误时为 true；已安全拷贝的前缀仍保留（G2） |
| `stop` 在 owner 线程、disable 后再最终 drain、先 join 再用存储/解映射、全路径清理、不丢主失败 | `stop` 校验 owner tid；顺序 DISABLE → 置停止 → join → 统计 → 独占写 → munmap/close/munmap；`record_error` 保留第一条主失败，清理失败不顶替 |
| 停止后才写原始字节与 metadata、独占创建、检查写入、不覆盖证据 | 两个 `open(O_CREAT\|O_EXCL)` 先建齐才写；`write_all` 检查每次 `write`；已存在即 `output_exists` 且不写任何字节；start 每条失败路径都 join reader + 释放 |
| 不在收集循环里算哈希 | 全部哈希留给 main 的 launcher；本模块不算任何哈希 |

`stop` 之后的账目（不重写任何字节）：`walk_perf_records` 按 header 自述长度遍历，得出 8 字节对齐标志、`max_record_bytes`、尾部非整记录字节数，以及 `switch_records`/`switch_cpu_wide_records`/`lost_records`/`lost_samples_records`/`unknown_records` 五类计数。遍历失败只记 `malformed_stream`，**已写出的 raw 字节不受影响**。

## demo 用法（由 main 运行）

```
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread \
   -o wksim_perf_stream_demo wksim_perf_stream_demo.c wksim_perf_stream.c
mkdir -p /tmp/wksim-stream-demo && ./wksim_perf_stream_demo /tmp/wksim-stream-demo
```

- 只接受**已存在**的输出目录；默认文件名 `switch-stream.raw` / `switch-stream.meta.json`；
- 写前与写时都拒绝覆盖（`access` 预检 + `O_EXCL` 保证）；
- 4 × 150 ms 短 sleep（约 600 ms）；sleep 失败也会 `stop` 释放资源，但退出码保持失败；
- 事后独立回读：raw 非空且 8 字节对齐；metadata 含下列 11 项标记。demo 不修不写任何回读结果。

## 契约中不可实现或缺失之处（不静默变更，逐条给出本实现选择）

| 编号 | 问题 | 本实现的选择 |
| --- | --- | --- |
| G1 | "enable 前抓 owner TID/boot"未规定输出到哪 | 写入 `owner_tid`/`boot_id`；顺序为先读身份与 boot、再读时钟、再 RESET/ENABLE |
| G2 | 未说明 capture 不完整时是否写字节 | **写已安全拷贝的前缀**并置 `collector_complete=false` + 明确 `collector_errors` |
| G3 | 只写"128 data pages"，未定页大小与环字节数 | `128 × sysconf(_SC_PAGESIZE)`；metadata 记 `ring_bytes`，并要求与 `data_offset`/`data_size` 严格一致 |
| G4 | "10 ms 轮询"未作为 API 参数 | 编译期 `WKSIM_PERF_POLL_NS`，API 严格保持契约的两个函数 |
| G5 | "raw 时间戳落在 capture 外边界内"未规定由谁检查 | 写者不做（收集循环禁止解析），只发边界；离线验收负责判定。stop 只做**不重写字节**的账目（对齐标志、类型计数、尾部非整记录字节数） |
| G6 | 环回绕丢记录的检测未定义 | 4096 字节 ring 余量判据作为保守失效器并计数；契约自要求的"独立丢包/序列审计"留给离线验收。**回绕是被判为压力，不是被证明不可能** |
| G7 | `reader_policy` 类型未定 | 写实际读回的整数策略值 + `reader_policy_name` 文本 |
| G8 | API 未定义错误通道 | 补 `wksim_perf_last_error()`（线程本地只读）与结构化 `collector_errors`；删掉该声明不影响两个契约函数 |
| G9 | 契约未定义"如何证明无损" | **无法从本侧证明**：kernel 尚未发布的 `PERF_RECORD_LOST` 不会被 `PERF_EVENT_IOC_DISABLE` 冲刷。metadata 固定写 `losslessness_proven: false` + `losslessness_reason`；`collector_complete=true` 只表示"collector 自身零错误"，**不等于无损，接飞行继续阻断** |

## 缺的停哨兵条件（只说清缺口，不自行加入 sched_yield 之类的保证）

main 正在完善 stop 哨兵验证。本模块当前只声明"collector 自己跑完最后一趟"，不声明"内核不再产生记录"。要成为可飞行的无损判据，至少还需要以下条件，且必须由 main 定义并实测：

1. **写者静默判据**：一份可核验的协议，证明 DISABLE 返回之后内核不再向该 event 的环写字节（含软中断/延迟投递路径）。只有 `PERF_EVENT_IOC_DISABLE` 的返回码不构成该证明。
2. **head 二次读的震荡界**：允许在 DISABLE 后再读 `data_head` 并给出"至多再 drain 一轮"的判定规则；`sched_yield`/固定等待都只是启发式，**不得**写成保证。
3. **LOST 的账目规则**：若最终的 `PERF_RECORD_LOST`（或 `LOST_SAMPLES`）只在内核侧待发、永不发布，判据必须规定如何得知它存在、如何计入账目、以及此时 capture 应判为不完整而非成功。
4. **丢失计数下界**：无损只能以"丢包计数为 0 且序列区间连续"声明，因而需要内核侧可读的丢失计数（`PERF_FORMAT_LOST` 或 event fd `read()` 计数）与序列审计的对齐规则，当前契约未提供。

在 1–4 有明确答案之前，`losslessness_proven` 保持 `false`、`full_acceptance` 保持 `false`，飞行准入阻断。

## 待 main 验证项（本目录不能自证）

1. `cc -Wall -Wextra -Werror -pthread` 编译 `wksim_perf_stream.c` 与 `wksim_perf_stream_demo.c`（本机为 Windows/MinGW，无 `linux/perf_event.h`，无法在此编译）；
2. paranoid=2 下 `perf_event_open(pid=0,cpu=-1)` + `exclude_kernel=1` 实际是否可用（OMP 结论是"必须置 1"，未实测）；
3. `pthread_attr_setinheritsched(PTHREAD_EXPLICIT_SCHED)` 是否被接受，reader 读回是否确为 `SCHED_OTHER`/0，manager FIFO 优先级未被继承；
4. `meta.data_offset`/`data_size` 在 6.6 上的实际取值（现在必须严格等于 page 与 128 页，否则 start 失败——有意的严格化）；
5. 4 次短 sleep 期间确实出现完整 switch 对，raw 非空且 8 字节对齐；
6. `join_reader` 失败分支只能在故障注入下验证（正常路径 pthread_join 应成功）；
7. 128 MiB 预触的耗时/内存，以及独占创建在已有同名文件时确实失败且不覆盖。

## 本目录静态自检（非编译，仅结构核查）

- 三个文件括号/圆括号/方括号配平（剥离注释与字符串后）；
- `wksim_perf_reader` 体内不出现 `malloc/calloc/realloc/snprintf/fopen/open/write/read/mmap/ioctl/pthread_join/fprintf/printf/memmove`；
- `collect_available` 内不出现 `perf_event_header`、`record_size`，含 ring 余量判据、storage 余量判据与 `data_tail` release 发布；
- 无 `copy_one_record`、无 `struct wksim_perf_start_args`、无 `args.` 残留；`pthread_create` 使用 `&attr`；`PTHREAD_EXPLICIT_SCHED` 存在。
