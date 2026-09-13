# OMP PERF_FORMAT_LOST 丢失计数器审查（2026-09-13）

- 工作类别：new-development（独立 perf 诊断模块只读审查，无模型/控制/固件/UE 依赖）。
- 检出：`main` @ `9e8ba03e43627918d5fab28aa59765a02fb068d1`；f333316 祖先检查退出码 0（本轮复验）。
- 只审实际运行内核 tag `linux-msft-wsl-6.6.87.2`，不据 5.15 或上游泛化。

## 锚定对象（本轮全部独立复核）

- tag → commit `427645e3db3a8896714f22a3d3fe0c3f7b317ad4`（GitHub ref API 确认，轻量 tag 指向该 commit）。
- `kernel/events/ring_buffer.c` blob `52de76ef8723b86d571e470d9fbfecd3cee3829b`、`kernel/events/core.c` blob `b710976fb01b1781737f8a9ebf3a5fc3f708c158`：按 `sha1("blob <len>\0"+content)` 重算，与给定值逐位一致。
- probe 源码 SHA256 `93a95a4aa8d02cfcf5eedfd9abeb4db76bf80b92dda85fd2f7ecf8afe84e9b4a`：与本地文件一致。
- UAPI：同 tag `include/uapi/linux/perf_event.h:363` `PERF_FORMAT_LOST = 1U << 4`（read_format=16 成立）。

## 内核源码因果（基于上述 blob 行号）

1. 计数点：`ring_buffer.c:177`（rb->paused 分支）与 `:260`（无空间 fail 分支）均为 `local_inc(&rb->lost); atomic64_inc(&event->lost_samples);`——rb 上每次输出失败同时进 LOST-record 计数与可读取计数，单调不丢。
2. sideband 覆盖：`core.c:9081 perf_event_switch_output → perf_output_begin → __perf_output_begin` 同一 fail 路径；per-task 事件（`ctx->task` 分支）发 `PERF_RECORD_SWITCH`。故 DUMMY+context_switch(sample_period=1) 的 sideband 丢失计入该计数器。
3. 读取路径：`core.c:5667-68 perf_read_one` 无条件 `values[n++] = atomic64_read(&event->lost_samples)`，不检查事件状态 ⇒ DISABLE 后读取有效（组读路径 5596/5603、7271/7308/7323 同语义）。
4. RESET 语义：`core.c:5759 _perf_event_reset` 只清 `event->count` 并更新 userpage，**不回零 lost_samples**；计数器自 fd 生命周期累计，仅靠新建 fd（kzalloc）归零。probe 未演练 RESET。
5. 继承语义：`ring_buffer.c` begin 开头 `if (event->parent) event = event->parent;` 先于 rb 与计数操作 ⇒ inherit=1 时子事件丢失计入父事件计数器；本模块 inherit=0，单事件单 rb。
6. 不计数缺口：`rb == NULL` 时 `goto out` 不增加任何计数——mmap 之前的输出尝试静默不计；当前 recorder 先 mmap（c:791）后 ENABLE（c:909），已覆盖，该顺序必须保持。

## 既有原件复核（receipt，boot b3fa43aa，kernel 6.6.87.2-microsoft-standard-WSL2）

- normal：2 次睡眠，DISABLE 后 read 得 16B，`kernel_lost=0`，ring 4 条 SWITCH（head=128=4×32, tail=0），0 条 LOST——无损情形无误报。
- overflow_disabled_without_drain：1 页 ring、全程不 drain、256×1ms 睡眠（应产 512 条），DISABLE 后 read 得 `kernel_lost=385`；ring 内 head=4064 tail=0、127 条 SWITCH、**0 条 LOST**；127+385=512 算术闭合。证明"永不发布的挂起丢失"可被 read16 读出——正是 LOST-record/哨兵机制看不到的情形。
- probe 自检严格：tail!=0、head 越界、非整记录、queued LOST>0 均判失败；raw 以 O_EXCL 落盘。

## 能否替代哨兵：可以（仅就完整性职能），且更强

- 哨兵只认证 end<=sentinel_before 的窗口、tail 不认证，且看不到挂起 LOST（见 omp-stop-sentinel-review-20260913.md 第 5/6 条）；DISABLE 后 read16 覆盖整个使能区间含 tail 与挂起丢失 ⇒ 完整性职能上严格更强、更简单，前一审的 pending-LOST 保留意见随之解除。
- 不替代的部分：counter==0 不证明 reader 把已发布字节全部拷走；reader 侧仍靠 recorder 自有守卫（storage/headroom 压力、malformed walk、几何、join 所有权保留），内容侧仍靠 consumer 结构校验（身份、交替、边界）。reader 停滞 ⇒ ring 填满 ⇒ 内核丢失被计数；收尾停滞由 join/final-drain 设计覆盖。验收谓词应为 `collector_complete && kernel_lost==0 && 既有全部检查`。

## 结论：条件性接受

机制本身无阻断项。采纳（替换哨兵）须满足全部条件：(a) 仅在上述 pinned blob + 本机 probe 双重验证的内核上有效，换内核必须重验 177/260 计数点与 5667-68 读路径；(b) 当前 recorder 未设 read_format 也从不 read（c:760-776 attr 无 read_format）——集成属于 recorder/consumer 代码变更（新增 meta 字段与拒绝规则），需另起实现派单并在 pinned 内核上重跑 native 验证，本只读审查不改代码；(c) 仅在 DISABLE 后、close 前读取，EINTR 重试，运行中读数仅为参考（累计值）；(d) 不得依赖 RESET 归零计数器，每次捕获用新 fd；(e) 保持 inherit=0、不用 SET_OUTPUT、mmap 先于 ENABLE。集成并重验前，现有哨兵证据仍是已接受基线，两份结论并存不冲突。
