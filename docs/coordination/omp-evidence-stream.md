# OMP AsyncEvidenceStream 独立验证（主会话重写版）

日期：2026-09-11。范围：仅改 `validation/test_evidence_stream.py` 与本文；实现
`Simulator/wksim_runtime/evidence_stream.py` 未触碰（主会话所有）。不运行
ROS/硬件/构建；不 nested/commit/push。

## 结论：实现可冻结

当前实现经独立逐条验证，**未发现缺陷**。旧版留存于
`validation/coordination/evidence-stream-before-parent-review.txt`（未动）。

## 接口事实核验（实读 + 实测）

| 要求 | 实现位置 | 验证 |
| --- | --- | --- |
| write(str) 返回字符数；summary 计 UTF-8 字节 | `write` 返回 `len(text)`（:101）；`_submitted/_written` 为字节 | 实测 `write("中文\n")==3`，summary submitted/written=10 |
| 单 producer、主线程不阻塞 | `put_nowait` + 立即失败（:96-99） | 满队列写入 1s 内显式失败且不丢记录 |
| close 单一 monotonic 期限、无 Timer | `deadline=time.monotonic()+...`（:108） | 超时负例有界（0.3s 期限实测 <5s 返回） |
| 正常 close 有界等待 accepted tail 入队 | 尾部 put 循环 20ms 片直到期限（:113-120） | 暂满/尾部释放后完整收尾测试通过 |
| producer_done 后阻塞 I/O 恢复仍能退场 | `_done` Event + `queue.get(timeout=.02)` 轮询退出（:54-57,125） | 超时后释放 writer，线程最终退出且失败仍锁存 |
| 只有后台线程关闭 fd | `_run` finally `_closer(fd)`（:72-75）；主线程无 close fd 路径 | `_closer` 注入：真关 fd 后抛错 → 不 complete |
| partial write 逐次累计 written | `_written+=count` 每次调用（:68） | 写 3 字节后 I/O 报错 → written==3/submitted==10 |
| close 错误锁存 | `_close_outcome`（:134） | 二次 close 重抛同一错误；成功幂等 |
| inf/NaN 超时拒绝 | `math.isfinite` 检查（:31） | inf/nan/-1/bool 全拒 |
| O_EXCL 不覆盖原件 | flags（:42-43，含 O_BINARY） | 原件保留测试通过 |
| summary 含 io_calls/max_io_wall_ns | :64-65,144-145 | 字段存在且计数/计时实测非负 |

## 测试（同一公开接口；事件同步、无随机 sleep）

`python -B -m unittest validation.test_evidence_stream`：
**Windows 14/14 OK（0.52s）；WSL 14/14 OK（0.47s）**。

新增事件同步负例：暂满队列+close 中释放 writer 后完整收尾不误失败；
close 超时后释放 writer 线程最终退出但失败锁存；partial 3 字节后 I/O 错
written==3；`_closer` 真关 fd 后抛错不 complete；非有限超时拒绝；满队列不阻塞
且永久 failed；原件不覆盖。修正了旧测试的错误镜像期望（write 返回值按字符数）。

## 观察项（非缺陷，可冻结）

- 容量先按字符数提前拒绝必然超限的输入，再按UTF-8实际字节数严格检查；接受条件仍是字节容量上限。
- 单 producer 为文档约定，实现未加锁；多生产者混用不在合同内。

## 历史说明

验证过程中两次失败均为测试侧错误（I/O 错负例的竞态等待、_closer 用例在 close 前
等线程退场），非实现缺陷；已修正为事件同步顺序。
