# CodeBuddy OMP perf-counter 两份历史审查的历史语境绑定（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时权威 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（写作时点的当前基线）。架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 与两份审查所记源检出 `9e8ba03e43627918d5fab28aa59765a02fb068d1`、收据 `source_head` `1b3dfdcc106be18bcff8ff0e69269f6c7eab755d` 均只以 `git merge-base --is-ancestor` 祖先检查绑定（写作时点对 HEAD 退出码 0）——**本批次对 HEAD 一律用祖先检查，不做永久 HEAD 相等断言**；本批次提交后 HEAD 前进不使本登记失效。

## 0. 本文件的地位

本文件只做一件事：把两份 OMP perf-counter 审查**按字节绑定**为历史语境（superseded historical context，KEEP），并登记其结论被内核计数器集成取代后的效力边界。它自身不构成任何验收、批准、收口或复核记录；被绑定文件同样不构成这些。本文件为纯只读复核产物：未修改被绑定文件或任何既有 tracked 文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未提交 Git、未触碰真实 index；未联网。

**显式边界**：本批次不关闭任何 MIXED/G6/Full 结论，不构成 #84 收口，不重跑 #83；`validation/coordination/perf-counter-integration-20260913-01/main-verdict.json` 载明 `classification=diagnostic_only`、`architecture_acceptance=false`、`full_acceptance=false`，本登记原样保留、不升格。tracked 实时合同 `docs/coordination/perf-stream-contract-20260913.md` 是**活指针**，在本批次候选之外，本登记只引用、不绑定、不取代它。

## 1. 历史语境绑定（字节级，写作 HEAD 现场重算）

| 被绑定文件 | SHA256 | bytes |
| --- | --- | --- |
| `docs/coordination/omp-perf-counter-integration-review-20260913.md` | `9e4a857bb52fc740e25085cb955879f96942f29663a360c802b45e07dab50b2c` | 5601 |
| `docs/coordination/omp-perf-lost-counter-review-20260913.md` | `e35ba529ae1eb18eb04c591f8bec2aea7f10c1a96ee02c1db56cf696dfcfef39` | 4890 |

两份均 tracked、工作树干净。裁决：**KEEP，作为被取代的历史语境**（superseded historical context）；绑定复核 P1=0 / P2=0；唯一材料缺陷为 P3 检出行不一致（§6），历史性、与 perf 源绑定无涉。

## 2. 快照身份跨 evidence 目录逐位一致（写作 HEAD 现场重算，HEAD 树字节与工作树一致）

| 逻辑对象 | SHA256 | bytes | 出现的 tracked 位置（逐位一致） |
| --- | --- | --- | --- |
| recorder `wksim_perf_stream.c` | `aa807f3baaafcd64ed6174a49f8010b49798a74d139ead2d4eb69eafa503c1d2` | 55245 | `ds-perf-stream-recorder-20260913-01/`；`perf-counter-integration-20260913-01/sources/` |
| header `wksim_perf_stream.h` | `ef1eabf247107098dc59a314d99b8fc82d4c54dbddd58d645bcec35141a12823` | 7318 | 同上两处 |
| consumer `perf_stream_consumer.py` | `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc` | 29362 | `ds-perf-stream-consumer-20260913-01/`；`perf-counter-integration-20260913-01/sources/` |
| probe `lost_counter_probe.c` | `93a95a4aa8d02cfcf5eedfd9abeb4db76bf80b92dda85fd2f7ecf8afe84e9b4a` | 4579 | `perf-lost-counter-20260913-01/`（顶层与 `sources/`） |
| superseded `superseded-sentinel-source.c` | `49303dab8cea513db3891924fa51813b441ca2e62fc038683ae6b775d0ad7b4d` | 57916 | `perf-counter-integration-20260913-01/` |

上述 SHA 与两份审查所记、各 receipt `source_sha256`（integration-01 `receipt.json` 的 recorder/header、`main-verdict.json` 三钉、`final-consumer-check.json` 的 consumer 钉、lost-counter `receipt.json` 的 probe 钉）逐位一致。两份审查的行号锚均以这些快照字节为准。

## 3. 收据算术与 consumer 钉（写作 HEAD 现场重读）

- `perf-lost-counter-20260913-01/receipt.json`（SHA256 `9bb5a22c8327b4de518d5283d466d89fc05fb5036bfb0273dfbd0dda0b255f4f` / 7177 B）：内核 `6.6.87.2-microsoft-standard-WSL2`、boot `b3fa43aa…`、`read_format=16`；normal `kernel_lost=0`（ring head=128=4×32、tail=0）；overflow_disabled_without_drain `kernel_lost=385`、`queued_records=127`、head=4064 tail=0——**127+385=512 算术闭合**（应产 512 条），0 条 LOST。raw 原件 tracked：`capture/normal.raw`（128 B，`c46d039bd5bc6daf043e31242b2608b4ee7076eaa2fcb509d78544d4a8525488`）、`capture/overflow_disabled_without_drain.raw`（4064 B，`e096de8815f769e90ee3d985f879ff43a9fa314a50a0151c49f10a36ba5c0a97`）。
- `perf-counter-integration-20260913-01/final-consumer-check.json`（SHA256 `f7caf584ccf013503dcd011540634306345b909fb8d6b8790f586e9282cb2ebc` / 881 B）：consumer 钉 `dee9a3b5…`；normal exit0（raw `553b29e3…`、8 records / 4 pairs）；loss exit3 `kernel_loss_counter_nonzero` detail 26471——与两份审查所记逐位一致。
- `perf-counter-integration-20260913-01/main-verdict.json`（SHA256 `4fcd7a6a217fb8e57e598a1b50bebf94e2c1181ab9e8c2f6d0c41bb7f15ebb96` / 3174 B）：`source_head=1b3dfdcc…`、`diagnostic_only`、`architecture_acceptance=false`、`full_acceptance=false`、recorder/header/consumer 三钉、6 编译 + 5 fault 程序、normal `kernel_lost_count=0`、pending_loss 16383 条全 SWITCH / 0 条 LOST / counter 26471。
- `perf-counter-integration-20260913-01/consumer-receipt.json`（SHA256 `dc5476513cadb23e2fefb82c62d4e672c00160335c64b184dd136f621407518e` / 6290 B）与 `-02/consumer-receipt.json`（SHA256 `6e246ec94eda958de44f348120fc547cc44385aaad635cbb19aa108cedc6e351` / 6290 B）：各 17 个反例、failures=0（`inspect_legacy` exit0、`required_legacy` exit3 等与审查 §12 记录一致）。
- `perf-counter-integration-20260913-01/receipt.json`（SHA256 `66a29ed985491b1884c190f53adbc2ca5676f874fbc064758ad4843f46fc9769` / 8396 B）：`source_head=9e8ba03e…`、`source_sha256` 钉 recorder `aa807f3b…` / header `ef1eabf2…`。

## 4. 机制内容锚（对 §2 快照字节逐行核验成立）

- recorder（aa807f3b）：`WKSIM_PERF_FORMAT_LOST (1ull << 4)`（c:47）→ `attr.read_format`（c:754）即 read_format=16；`attr.inherit = 0`（c:757）；ring `mmap`（c:780）先于 `PERF_EVENT_IOC_ENABLE`（c:898）——无 rb==NULL 不计数窗口；stop 路径 clock+`PERF_EVENT_IOC_DISABLE`+clock（c:1087±），其后、`close(stream->fd)`（c:1210）之前 read16（c:1101 起，EINTR 重试上限 8 次），短读/失败/计数非零均记 `WKSIM_ERR_CAPTURE_INCOMPLETE`（c:1107-1116）；meta 序列化在清理后，`lost_read_ok` 为假时 count 写 `null`（c:1229-1232）；fail-closed 完整性谓词 `complete = (error_count_now(stream) == 0) && disable_ok && …`（c:1361）。
- consumer（dee9a3b5）：`validate_kernel_loss_counter`（py:147-166）在 `validate_metadata` 内、decode（py:499 调用）之前执行（py:238）；字段缺失/部分缺失、`read_format` 非 int 16、`read_ok!=True`、`read_bytes!=16` 或 errno!=0、count 非 [0,2^64-1] 纯 int、count>0（`kernel_loss_counter_nonzero`）各有独立 reason；`--require-kernel-counter`（py:482）不满足时以 `kernel_loss_counter_required` 拒绝（py:497-498）；验证通过时 `window_completeness` 方法标注 `post_disable_kernel_event_loss_counter`（py:505）覆盖整个内层区间。
- 内核前提：lost-counter 审查钉 tag `linux-msft-wsl-6.6.87.2` → commit `427645e3db3a8896714f22a3d3fe0c3f7b317ad4`、blob `52de76ef…`/`b710976f…`、UAPI `PERF_FORMAT_LOST = 1U << 4`；换内核必须重验（两份审查条件 a）。

## 5. 取代关系与文档债（原样保留，不代办）

- **哨兵时代机制已被内核计数器集成取代**（仅就完整性职能；counter==0 不证明 reader 拷走全部已发布字节——内容侧仍靠 consumer 结构校验、reader 侧靠 recorder 自有守卫）。superseded 源 `superseded-sentinel-source.c` tracked 在案；现行 recorder 全文无哨兵残留。集成前哨兵证据是当时的已接受基线，两份结论并存不冲突（lost-counter 审查原话）。
- **文档债**（两份审查条件 c，仍在）：header G9（ef1eabf2 h:80-84）仍写"flight admission stays blocked until the stop sentinel is defined"（哨兵已删）；consumer docstring（dee9a3b5 py:15-17）仍只写 32 字节记录表述、未记计数器规则。
- 旧捕获（无 kernel 字段）维持 inspection-only；任何依赖完整性的消费方必须加 `--require-kernel-counter`。

## 6. P3：检出行不一致（历史性，与 perf 源绑定无涉）

两份审查记 `main` @ `9e8ba03e43627918d5fab28aa59765a02fb068d1`，而 `main-verdict.json` 收据 `source_head` 为 `1b3dfdcc106be18bcff8ff0e69269f6c7eab755d`（integration-01 `receipt.json` 则记 `9e8ba03e…`）。现场核验：两者均存在、均为当前 HEAD 祖先，且 `9e8ba03e` 为 `1b3dfdcc` 的祖先（merge-base = `9e8ba03e`）。该不一致**不触及** perf 源绑定：本登记所有源/收据身份均以 tracked 快照字节（§2/§3）为准，与任何检出行无关。历史性登记，不改写两份审查原文。

## 7. 字节同一性前提（.gitattributes）

六个 perf evidence 目录（`perf-lost-counter-20260913-01`、`perf-counter-integration-20260913-01/-02`、`ds-perf-stream-recorder-20260913-01`、`ds-perf-stream-consumer-20260913-01`、`ds-perf-stream-fixtures-20260913-01`）各自 tracked 一份 `.gitattributes`，内容均为 `* -text`——目录内字节按原样入库，工作树字节 = HEAD 树字节。仓库根 `.gitattributes` 未设全局 text 规则、也未列这些路径（`git check-attr text` = unspecified），同样不产生换行转换。§1/§2/§3 的逐位绑定以此为前提。

## 8. 不声称清单（显式）

- 未把历史语境升格为当前执行、验收、批准或收口；两份审查是"条件性接受"的历史记录，其条件（pinned 内核、不变量保持、文档债登记、`--require-kernel-counter`）不因本登记而视为已满足或已终止；
- 未声称对当前 HEAD 树的任何源文件成立——recorder/consumer 现行 HEAD 状态本登记未审计，行号锚只对 §2 快照字节有效；
- 不关闭任何 MIXED/G6/Full 结论，不构成 #84 收口，不重跑 #83，不触发/建议/替代任何工单重跑；
- 不取代、不绑定 tracked 活合同 `docs/coordination/perf-stream-contract-20260913.md`；实时 perf-stream 合同仍在本批次候选之外；
- 未修改被绑定文件或任何 tracked 文件；未触碰真实 Git index；未联网；未运行任何 native/构建/模型程序。
