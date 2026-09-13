# ds-perf-stream-recorder-20260913-01：OMP 接管修复记录

D 任务终态 failed，模块写入权移交 OMP。本文件先钉住接管前字节，再列最小修复。

## 接管前 SHA-256（D 最后状态，逐字备份不存在——原件就地修改，此表为身份凭据）

| 文件 | 接管前 SHA-256 |
|---|---|
| `wksim_perf_stream.c` | `857f0cefb7147481f83f4702a8ffcc9a619ae62a4fa66703e79e4c4ff5e437a6` |
| `wksim_perf_stream.h` | `96a69a8a97b2502547f4ff5727eb6b2a96eb08ff0d6b4ad3cd1f922c9ccb3f45` |
| `wksim_perf_stream_demo.c` | `9b0ee95baa6e22d021cc61025e4b69cd735022d9f0bfb7a74d8a67f65cd3540b` |
| `README-perf-stream-recorder.md` | `191ee27646a4347a77d4dd081e1ab155dc6ae734da73ba1eff2a57e863c402f3` |

## 独立审阅结论：D 已修复大部分；四处实修

已正确、未动：reader 显式 attr 语义+readback 验证、handle 内 mutex/cond ready 握手、错误数组双线程 mutex+join 后 owner 提升、ring/storage 双 guard、collector 逐字节原样复制零解析零分配零 I/O、copy 后 release 发布 tail、stop 的 join 失败保留所有权。

修复（全部最小化）：

1. **编译阻断（同名遮蔽）**：`start()` 内 `pthread_attr_t attr` 与 `struct perf_event_attr attr` 同域重声明，-Werror 下不可编译 → pthread 侧改名 `thread_attr`。
2. **握手锁释放漏洞**：`cond_wait` 失败后 owner 仍持 `ready_lock` 且不再解锁，随后 join 会被正在发布的 reader 卡死 → 拆 `lock_rc`/`wait_rc`，持有即必解锁。
3. **start 失败路径 join 未查**：六处先 `release_handle`+`free` 再看都不看 join 结果；join 失败=reader 可能仍在写 storage/ring → use-after-free → 新增 `start_abort()`：stop_requested→join；join 失败（非 ESRCH）保留全部资源、故意泄漏 handle 并记 WKSIM_ERR_JOIN（start 无法交还 handle，泄漏是唯一安全选择）；ESRCH（线程已消失）在 `join_reader` 内显式记录异常后按已终止处理。
4. **计数循环幻影记录**：`count_perf_records` 第二遍对 walk 已判定的尾部残字节仍按 header 读 → 计数限定在 walkable 前缀内。

## 审过但保留的冗余

reader 内 `pthread_setschedparam(self, SCHED_OTHER)` 与 EXPLICIT_SCHED 创建重复但无害（readback 仍校验），为控制 diff 未删。

## 主会话编译命令（本模块不编译）

```text
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread \
   -o wksim_perf_stream_demo wksim_perf_stream_demo.c wksim_perf_stream.c
```

## 范围声明

哨兵/完整性闭合未实现：metadata 仍 `losslessness_proven=false`，合同级阻断维持（见 omp-perf-stream-review-20260913-01/REVIEW.md `53d3b958…`），不接飞行。未做编译/native/WSL perf/模型。
