# ds-perf-overhead-driver-20260913-01：配对 self-thread recorder 开销合成驱动

status: **短时 native admission 已通过，完整时长未运行**。交付时 C 源码尚未运行；main 随后在私有 Ubuntu-22.04 目录编译相同 `bench_overhead.c` 字节，并在修正故障工具后完成短时 smoke、严格 consumer 与原生故障反例。Python 分析器的作者测试为 25 checks、0 failed。逐字节被中断的上一版草稿保留在 `historical-draft/`，**不作为交付物**，仅用于追溯。

工作类别：new-development。实际 cwd `C:/Users/PC/Documents/odid编译/wksim`，分支 `main`，HEAD `0857cd95ed54bb976ef541bbb8462bde29c456e5`，`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` 退出码 `0`。本次只改本目录文件，不改 recorder/consumer/`perf_capture.py`、不接线 runner、不提交。

## 本轮主审修复（对应 `perf-overhead-main-review-20260913-01/review.json`）

| 编号 | 缺陷 | 修复 |
| --- | --- | --- |
| 1 | `stop_rc != 0` 且 handle 已清空时仍可能写出输出并 exit 0 | 失败谓词显式加入 `enabled && (start_rc != 0 \|\| stop_rc != 0)`；仅 `failure` 为空才写文件并 exit 0 |
| 2 | start 之后时钟/CPU 采集失败直接 return，漏过 stop | 统一单一 owner 出口：`failure` 记录原因 → 无论何种失败都在同一线程调用 `wksim_perf_stop` → 再判定写出；所有失败路径都经过 stop |
| 3 | 两个 `FILE*` 先一起打开再检查；`fclose(jf) \|\| fclose(cf)` 短路跳过第二个关闭 | 逐个打开/写入/关闭，各自独立检查；两个 `fclose` 都必然执行，随后合并结果 |
| 4 | 分析器可用互相匹配但截断/改标的两场冒充请求负载 | 新增 `iterations == duration//period` 校验与两场 `measurement.body_checksum` 一致校验（`iteration_count_mismatch`、`body_checksum_mismatch`） |
| 5 | `min(gaps)` 对单行（`duration == period` 合法）取空序列 | `describe` 改为先收集 gaps，单行时报告 `min_actual_start_gap_ns = period` 并置 `min_actual_start_gap_defined=false` |

保留未动的性质：`earliest = max(ideal, previous_actual + period)` 的无追赶语义、`timing.csv` 原始顺序、`clock_nanosleep(TIMER_ABSTIME)` 绝对 deadline、全部 C 返回码与所有权规则（含保留 handle 时的 `retained` 处理）、完整记录、输入上界、以及 CPU 测量区间确实排除 start/stop。

## main 短时 native admission

证据位于 `validation/coordination/perf-overhead-native-admission-20260913-01/receipt.json`。main 在同一启动器内先确认 Ubuntu-22.04 与 RflySim-20.04 均 `found=[]`，入口核验 boot 和前检新鲜度后，在 `/root/wksim-overhead-native-1npujbah` 运行 17 个独立进程；全部未超时、PGID 为空且 boot 前后一致。

- recorder 共享库、普通 benchmark、故障 benchmark 均以 `-Wall -Wextra -Werror` 编译成功；共享库导出三个预期 API。
- 320 ms / 8 ms 的 disabled、enabled 与无注入 fault baseline 均完成 40 行；disabled/enabled 的 body checksum 相同。离线分析成功，enabled raw 为 80 records / 40 pairs，严格 consumer 使用 `--require-kernel-counter` 通过。
- start_begin、start 返回后时钟、CPU 基线、CPU 收尾四类注入均 exit 3，并由 stop wrapper trace 证明到达统一 owner stop 出口；没有 result/CSV 被接受。
- `fclose` 第二次报告失败时两个 close 均被观察且 exit 3。真实 stop 成功并清空 handle 后由 wrapper 报告 -1 的反例也 exit 3，raw/metadata 仍由严格 consumer 验证为 80 records / 40 pairs，result/CSV 未生成。

这些是 320 ms 合成 smoke 与清理合同验证；数值差异包含两个进程间的调度噪声，不能外推完整时长，更不构成真实 MIXED 或 Full 结果。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `bench_overhead.c` | 单进程 = 单行。合成周期循环（复现 `begin_group()` 释放算式）＋可选 recorder 包夹；只写 `result.json` 与 `timing.csv` |
| `analyze_overhead.py` | 纯 Python 配对分析：同一请求负载、`iterations == duration//period`、`body_checksum` 一致、行数完整、时钟非下降、启动间隔未压缩；只输出测量差值 |
| `test_analyze_overhead.py` | 纯 Python 合成测试：成功路径、单次迭代边界、25 项断言（含 18 项拒绝） |
| `fault_inject.c` | **仅故障注入**用链接包装器（`--wrap=clock_gettime/getrusage/fclose`），不进入正常测量路径；由 main 按需编译 |
| `historical-draft/` | 被中断的上一版草稿（C/Python/测试），保留原样，不属于交付 |

## 循环语义（与真实 runner 一致的部分与不一致的部分）

```text
ideal[k]    = start_ns + k * period_ns
earliest[k] = max(ideal[k], actual_start[k-1] + period_ns)     # k>0；k=0 时 = ideal[0]
actual[k]   = 循环真正到达 earliest[k] 的时刻
```

`earliest` 从**上一次实际启动**起算，因此迟到不会被补偿：一次迟到按常量偏移向后传播，请求计划不会回退。本驱动**不实现**真实 runner 的 health 回调、4-tick 分组、rate 变更与 lateness latch，只复现上述释放算式与“无追赶”性质。等待使用 `clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME)`；每次 clock/sleep 失败都被记录并使该行判为不完整（退出码 3，不写任何输出文件）。

## 约束与边界

- `MIN_PERIOD_NS=1ms`、`MAX_PERIOD_NS=1s`、`MAX_DURATION_NS=1h`、`duration/period <= 1000000`（固定数组上限）；`iterations = floor(duration/period)`，无部分区间。
- `timing.csv` 每行 `index,ideal_start_ns,earliest_start_ns,actual_start_ns,end_ns`，**按原始顺序**写出，不排序、不重写；百分位与差值由离线分析计算。
- CPU 窗口：`getrusage(RUSAGE_THREAD)` 与 `getrusage(RUSAGE_SELF)` 在 `start` 返回后读取基线、在调用 `stop` 之前读取结束值，因此 start/enable/disable/stop 跨度**确实被排除在 CPU 窗口之外**（不是声明式排除）。recorder 的 start/stop 跨度单独保留在 `result.json`。
- 输出目录必须**已存在且为空**；`result.json`/`timing.csv` 用 `wx`（`O_EXCL`）独占创建，`switch.raw`/`switch.meta.json` 由 recorder 自己独占创建。已存在即拒绝，不覆盖。
- recorder API、start/stop 归属与错误检查原样保留：`start`/`stop` 返回非 0 且 handle 非 NULL 即“保留所有权”，此时不触碰、不重试、不释放，`retained` 置真并退出非 0。`start` 失败不写任何测量。
- 不做哈希（`result.json` 不含 SHA256）、不解析 recorder metadata、不判定无损：这些是 main launcher 与既有 strict consumer 的职责；`switch.meta.json` 验收请用 main 的 `--require-kernel-counter` 流程。

## main 运行步骤（编译与运行都由 main 执行）

前检、两 WSL 核查与启动按既有策略（`docs/coordination/module-delivery-policy-20260912.md` 规则 14）。本目录不自行启动任何 native 进程。

```bash
REC=<recorder-dir>            # 含 wksim_perf_stream.c/.h（SHA256 见下）
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -I "$REC" -o bench \
   bench_overhead.c "$REC/wksim_perf_stream.c"

# 需要 main 提供的实际数值；两行必须使用完全相同的 duration/period
DUR=360000000000 PER=8000000   # 示例位形：360 s / 8 ms；不是通过门槛，只是示例
for MODE in disabled enabled; do
  DIR="run-$MODE"; mkdir -p "$DIR"       # 必须为空
  ./bench "$DUR" "$PER" "$MODE" "$DIR"
done

python3 -B analyze_overhead.py run-disabled run-enabled overhead.json
```

- 两个模式各跑一次、目录分别清空；`disabled` 行不创建 `switch.raw`。需要复核顺序效应时再跑一组 `enabled` 先、`disabled` 后，但**不同进程行不可直接比较为同一测量**。
- `result.json` 的 `body_checksum` 两模式应相同，可用于确认负载一致。
- recorder 原始证据（`switch.raw`/`switch.meta.json`）与来源哈希绑定、kernel loss 计数判定由 main 按既有入口完成；本目录不替代。
- 退出码：`2` 参数/路径/已存在；`3` 采样不完整（sleep/clock/spans 失败或所有权被保留）；`0` 两文件写出。

## 运行器与 CLI

```text
bench <duration_ns> <period_ns> <disabled|enabled> <existing-empty-dir>
python -B analyze_overhead.py <base_dir> <variant_dir> <out.json>   # 0 / 3 / 4
python -B test_analyze_overhead.py                                  # 0 / 1
```

## 故障注入（由 main 编译与运行；本目录不声称跑过 C）

`fault_inject.c` 只在故障用例里链接。故障构建链接私有共享库，使 `--wrap` 只拦截 benchmark 对象的调用；recorder reader 线程内部的时钟调用不经过这些计数器，避免故障工具自身的数据竞争。未设环境变量时包装器逐调用转发真实实现。

```bash
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -shared -fPIC -I "$REC" \
   -o "$LIBDIR/libwksim_perf_stream.so" "$REC/wksim_perf_stream.c"
cc -std=c11 -O2 -Wall -Wextra -Werror -pthread -I "$REC" -o bench-fault \
   bench_overhead.c fault_inject.c -L "$LIBDIR" -Wl,-rpath,"$LIBDIR" \
   -lwksim_perf_stream -Wl,--wrap=clock_gettime -Wl,--wrap=getrusage \
   -Wl,--wrap=fclose -Wl,--wrap=wksim_perf_stop
```

| 用例 | 命令（`DIR` 必须是已存在的空目录） | 期望 |
| --- | --- | --- |
| 无注入基线 | `./bench-fault "$DUR" "$PER" enabled "$DIR"` | 与 `bench` 相同：exit 0，`result.json`、`timing.csv`、raw 与 metadata 均存在 |
| start_begin 时钟失败 | `WKSIM_FI_CLOCK_FAIL_AT=1 WKSIM_FI_TRACE_STOP=1 ./bench-fault ... enabled "$DIR"` | exit ≠ 0；实现仍会 start，随后 stderr 的 stop trace 证明统一清理出口；不接受 result/CSV |
| start 返回后时钟失败（缺陷 2） | `WKSIM_FI_CLOCK_FAIL_AT=2 WKSIM_FI_TRACE_STOP=1 ./bench-fault ... enabled "$DIR"` | exit ≠ 0；stderr 有 stop trace；不接受 result/CSV |
| start 之后 CPU 基线失败（缺陷 2） | `WKSIM_FI_GETRUSAGE_FAIL_AT=1 WKSIM_FI_GETRUSAGE_FAIL_WHO=process WKSIM_FI_TRACE_STOP=1 ./bench-fault ... enabled "$DIR"` | exit ≠ 0；stderr 有 stop trace；不接受 result/CSV |
| 结束时 CPU 读取失败 | `WKSIM_FI_GETRUSAGE_FAIL_AT=3 WKSIM_FI_GETRUSAGE_FAIL_WHO=process WKSIM_FI_TRACE_STOP=1 ./bench-fault ... enabled "$DIR"` | exit ≠ 0；stderr 有 stop trace；不接受 result/CSV |
| 关闭失败（缺陷 3） | `WKSIM_FI_FCLOSE_FAIL_AT=2 ./bench-fault ... disabled "$DIR"` | exit ≠ 0；stderr 报 `csv_close` 且同时记录 `fclose call 1 observed` 和 `call 2 observed` |
| stop 非零且 handle 已清空（缺陷 1） | `WKSIM_FI_STOP_REPORT_FAILURE=1 ./bench-fault ... enabled "$DIR"` | 先执行真实成功 stop，再报告 -1；exit ≠ 0，raw/metadata 可保留，不接受 result/CSV |

调用序号说明（`n` 从 1 开始）：benchmark 的 `clock_gettime` 第 1 次是 start_begin（start 前），第 2 次是 start_end（start 返回后），第 3 次是循环基准 `t0`；若较早调用失败，C 的短路求值会跳过后续同一采集链，后面的序号随之提前。`getrusage` 第 1–2 次是 start 后的 CPU 基线（SELF 后 THREAD），第 3–4 次是循环结束后的收尾读取（SELF 后 THREAD）；`fclose` 第 1 次是 `result.json`、第 2 次是 `timing.csv`。`WKSIM_FI_GETRUSAGE_FAIL_WHO` 取 `thread`/`process`/`any`/省略；注入器报告 `fclose` 失败时仍会真正释放流，不会由注入器自己泄漏描述符。

## 允许与不允许的结论

- `bench_overhead.c` 是**合成节奏循环**，不是仿真器、不是控制器、不是飞行。即使用真实 rate 窗口的 duration/period（例如 360 s / 8 ms）跑它，也**不能**据此声明真实整机/整飞行开销，也不能声明与 runner 等价。
- `analyze_overhead.py` 只报测量差值：无 PASS/FAIL、无阈值、无 `native_verified`。它校验的是“同请求负载 + `iterations == duration//period` + 同一 `body_checksum` + 完整行 + 时钟非下降 + 未压缩启动”，不证明 recorder 无损，也不构成飞行/架构/MIXED/G6/Full 验收。
- 已知干扰仍在：两个模式是**不同进程、不同时刻**，wall/CPU 差值含调度噪声、CPU 迁移与共租活动；`getrusage` 粒度可能大于循环时长，此时“小或零差值”是低于分辨率，不是零成本。

## SHA-256（本轮交付冻结值）

```text
bench_overhead.c            e51535a4dfce2107dbc9f8f3f30e68ee094a3a38bb72d1158160fede969df2c7
analyze_overhead.py         9da94c6fb9980953550e141797f6c56ae4f9e8482b641365db08518f68dd277e
test_analyze_overhead.py    c8ede1515beb6136a6406a0e550d70460fb7cc27d460c753766ada05cb12d79e
fault_inject.c              9208435d8f5a418213807b60b92564102e0d0adaccba7cb0673165410837b608
```

上一轮被主审的字节为 `bench_overhead.c 7771c590…`、`analyze_overhead.py 7976a623…`，与本轮不同；主审 5 项缺陷基于该草稿，本轮逐项修复后哈希如上行。`historical-draft/` 内文件不再变更。

依赖（只读，未修改）：

```text
validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c
  aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2
validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h
  ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823
```

## 遗留限制（不掩盖）

1. 短时 native admission 已验证编译、`clock_nanosleep`、perf recorder、严格 consumer 与故障清理；尚未运行完整时长的配对测量，因此没有长期扰动、整体开销或通过阈值结论。
2. `MIN_PERIOD_NS=1ms` 下限意味着 8 ms/360 s 位形可跑，但更细周期属于 spin 测试，本驱动拒绝。
3. 单线程、单输出目录；未测多进程并发或与其它负载共存时的表示。
4. `historical-draft/` 中的旧版含手写 SHA256/JSON 与排序采样，已知不符合本轮要求，仅作追溯，禁止据此继续开发。
5. `fault_inject.c` 的 `fclose` 包装按“报告失败但真实关闭”实现：它验证的是 bench 对失败返回值的处理，不模拟内核级关闭失败。
