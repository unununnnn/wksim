# OMP 停止哨兵有限窗口完整性审查（2026-09-13，修订 1）

- 工作类别：new-development（独立 perf 诊断模块只读审查，非新架构/飞行验收）。
- 检出：`main` @ `9e8ba03e43627918d5fab28aa59765a02fb068d1`；`git merge-base --is-ancestor f333316… HEAD` 退出码 0（已复验）。
- module/interface：self-thread perf raw 流与 `window_completeness`；依赖仅 Linux perf/pthread/stdlib，无模型/控制/固件/UE 接线。
- 审查对象与实测 SHA256（与 receipt 内 `source_sha256` 一致；git 索引中版本较旧，receipt 锚定的是工作区字节）：
  - `wksim_perf_stream.c` = `49303dab8cea513db3891924fa51813b441ca2e62fc038683ae6b775d0ad7b4d`（与派发给定值一致）
  - `wksim_perf_stream.h` = `ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823`
  - `perf_stream_consumer.py` = `ff087b9ec51fa53e9b08e20c2790f5779eaecf240e3dbd5b65c38136ac33d819`
  - `force_kernel_loss.c` = `49436a3307431d4df7eaa81c38a127cf4858b611e1276bd8824bb3f6ab1d2a0d`
  - receipt/demo/loss/consumer = `b196d2b4…` / `81f78037…` / `a4e03e01…` / `e3008198…`（全 64 位已核对，此处缩写）
- 修订 1：按复核意见精确化第 1 条停止顺序与第 6 条前缀因果；其余条目与验证结果不变。

## 核对结论（逐条，行号基于上述 SHA 的源码）

1. **ready 发布/停止清理时序：正确；停止文件顺序精确如下。** reader 在 `ready_lock` 下发布策略读回+ready（c:512-516），owner 确认后才 RESET/ENABLE（c:872-920）。stop 的精确顺序：哨兵→clock+DISABLE+clock→`stop_requested`（c:1181，置位在 DISABLE 之后，最终 drain 时生产者已停）→join→`settle_errors`→`count_perf_records`→主失败判定（c:1157-1213）→O_EXCL 打开 raw 与 meta fd（c:1217-1233）→**写 raw 字节并关闭 raw（c:1241-1258）→清理 munmap ring/close perf fd/munmap storage（c:1260-1286）→之后序列化 metadata 并写 meta（c:1288-1407）→关闭 meta（c:1409-1413）**→`complete` 终判（c:1421-1440）。meta 刻意在清理之后序列化，使 `lifecycle.munmap_ok/close_ok` 与清理期 `collector_errors` 进入证据；cleanup fault 例（注入 2 次 munmap 失败）的 meta 确实携带这两错且 stop=-1——这正是该顺序修过的真实缺陷。join 失败不写任何文件、不释放、所有权保留（c:1183-1193）。
2. **只认证 end<=sentinel_before 窗口：成立。** 记录端写 `verifiable_window_end_ns = sentinel_before_ns`（c:1359）；消费端强制相等（py:387 `sentinel_cutoff_mismatch`）并拒绝 `end_ns > verified_until_ns` 的窗口（py:509-511 `window_after_stop_check`）。真实 demo 原件复算：verified_until=54634401931=sentinel_before，唯一位于其后的 pair（seq 9，哨兵睡眠自身）不被认证。
3. **最后 tail 不作完整性声明：成立。** meta 固定 `losslessness_proven: false` 并附原因（c:1332-1335）；consumer 固定 `stream_completeness_proven: False`（py:559-563）。两个真实 meta 均如此。
4. **遗漏拒绝条件：审查范围内未发现。** decode 先于哨兵认证执行（py:501-503），已发布 LOST 必然否决认证；forced-loss 原件复跑确认 exit3 `record_lost_present`（offset=524256 size=48）。14 个合成哨兵例逐案复跑与 consumer-receipt 全部 MATCH；84 项回归复跑 0 失败；create/join/ring/policy/cleanup 五类原生 fault 收据与代码路径一致。
5. **压力注入覆盖面：覆盖"已发布 LOST"，不制造"DISABLE 时仍挂起的 LOST"。** 注入器在 copy 后、tail 发布前暂停 reader（memcpy 拦截，≥8192B 且目标在 storage 内），owner 20000 次真实 1µs 睡眠打爆 512KiB ring；恢复后 kernel 发布真实 LOST（id=2, lost=26376, size=48），raw SHA `fff8be28…` 复核一致；recorder stop=0、`collector_complete=true`、`lost_records=1`（按 G2/G5 分工由 consumer 拒绝）。ring 余量守卫由 `ring_copy_cases` 合成例覆盖。
6. **前缀认证的因果闭合（修订：原"前缀缺口"表述撤回）。** 适用前提：本模块固定 single-owner 线程、单个 DUMMY 软件事件（pid=0, cpu=-1）、`inherit=0`、不用 PERF_EVENT_IOC_SET_OUTPUT——因此全流只有一个 ring buffer 对象（任务迁移时 rb 随事件走，`event->parent` 重定向分支不触发），所有记录写入同一单调 `rb->head` 流。内核 v5.15 `kernel/events/ring_buffer.c::__perf_output_begin` 的因果链（本次已取上游源码逐行核对）：空间不足走 `fail:` 仅 `local_inc(&rb->lost)`，lost 计数单调不丢；下一次成功的 begin 先 `have_lost = local_read(&rb->lost)`，在同一次 `local_cmpxchg(&rb->head,…)` 预留里把 LOST 记录（`local_xchg(&rb->lost,0)` 清零）写在本记录**之前**（LOST 先于 payload `perf_output_put`），再由 `perf_output_put_handle` 的屏障后 `data_head` 一次性发布。**推论：哨兵 out/in 已成功发布 ⇒ 该 begin 已把此前全部 rb->lost 作为 LOST 记录写在更早字节位置 ⇒ 必在逐字捕获中 ⇒ consumer 必拒。** 故在以上前提下不存在"影响哨兵前前缀却永不发布的 LOST"，前缀认证闭合；原稿两句的表观冲突是表述错误，非机制漏洞。残留仅限两类：(a) 最后一条已发布记录**之后**的挂起丢失（tail，本就不认证，G9 措辞保留）；(b) 前提被破坏或原件被篡改——属范围外条件，不是前缀内已允许的缺口。forced-loss 中 16386 条 switch 在丢失 26376 条后仍干净交替，仅证明交替检查单独不足，检测依赖的正是上述 LOST 优先发布机制。

## 非阻断文档瑕疵

- c:996-999 注释称尾部不足一条记录"Not an error by itself"，但 `record_errorf(CAPTURE_INCOMPLETE)` 实际使 stop 失败（行为严格、方向安全，注释误导）。
- consumer docstring（py:15-17）仍称 raw 必须全是 32 字节记录，与 decode 按 type 分类后拒绝非 switch 的实际行为不符（行为已验证正确）。

## 结论：条件性接受（修订后维持，且前缀论证加强）

接受"end<=sentinel_before 窗口被认证、最终 tail 不认证、diagnostic_only"这一有限主张，条件：(a) 保持 `diagnostic_only`/`full_acceptance=false`，不产出飞行结论；(b) 完整性表述保留 tail 限界措辞，不得把 `collector_complete=true` 当作整条流无损证明；(c) 修正或登记上述两处注释/docstring 偏差；(d) 前缀认证仅在第 6 条所列前提（single-owner、单 DUMMY、no-inherit、no-set-output、单一 rb）下成立，改动事件配置须重审此因果链；跨 DISABLE 挂起 LOST 只涉及不认证的 tail，不构成前缀阻断项。
