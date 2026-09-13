# OMP 联合执行器微基准（隔离 ROS，无 FC/物理/UE）

日期：2026-09-11。目的：可信测量当前 `Task.pump` 模式
（`rclpy.spin_once(node, timeout_sec=0)`，已实读安装源证实每次调用
add_node+spin_once+remove_node）与显式 SingleThreadedExecutor 一次 add_node、
反复 spin_once(0) 的真实墙钟/线程 CPU 开销。**结果为诚实负结果：复用执行器
在本条件下没有收益。**

## 协议（主审修订后）

- 归属纪律（实读 `node.py` executor setter 与 `executors.py` add/remove 确认）：
  全局 spin_once 的 add_node 会经 `node.executor` setter 把节点从持久 executor 移走。
  每个 A（rclpy）批次前 `node.executor=None`；每个 B（持久 executor）批次前一次
  不计时 `executor.add_node` 并断言 `node.executor is executor` 且节点在
  `get_nodes()`；批次后 remove；A 后断言节点未留在持久 executor。两 executor
  从不同时持有节点。
- 有消息类：逐消息唯一序号发布，循环 spin(0) 直到该消息 callback 发生；
  每次 spin 记录是否执行 callback；两臂实际收到相同 400 条（100×ABBA×2 轮）；
  空 poll 数单列（各 399）；处理开销只比较 callback=True 样本。
- CPU 用 `time.thread_time_ns`（仅基准线程，不混入 DDS 后台线程）。
- 隔离：`unshare --net --ipc`、`ROS_DOMAIN_ID=77`、LOCALHOST 发现；probe 命名
  节点/话题（`wksim_executor_probe_<pid>`），不碰任何业务/飞控 topic；
  空队列类 3000 调用/臂；总墙钟 2.18s（上限 25s，未截断）；
  清理 remove_node + executor.shutdown + destroy_node + rclpy.shutdown。
- 旧失败证据 `joint-executor-benchmark-01.json`（含 traceback）原样保留未改。

## 实测结果（`validation/coordination/joint-executor-benchmark-02.json`，x 模式）

| 类/臂 | n | wall 中位 | wall p95 | wall p99 | 线程 CPU 中位 |
| --- | --- | --- | --- | --- | --- |
| empty / rclpy 每次 add-remove | 12000 | 27,853ns | 42,629ns | 91,922ns | 27,927ns |
| empty / 持久 executor | 12000 | 112,192ns | 166,790ns | 239,411ns | 52,735ns |
| with-msg / rclpy（callback 样本） | 400 | 44,522ns | — | — | 44,681ns |
| with-msg / 持久 executor（callback 样本） | 400 | 41,622ns | — | — | 41,768ns |

结论：空轮询下持久 executor 反而更慢（wall 中位约 4 倍；其 spin_once 每次仍重建
wait set）；有消息处理样本两臂相近（差约 3µs，callback 路径主导）。**不支持
"改持久 executor 能省出 rate 预算"的假设**；tracking-02 的残余 release 归因
仍开放。原始批次逐样本数据在证据 JSON 内。

## 复现命令

```powershell
wsl -d Ubuntu-22.04 -u root -- bash -c 'unshare --net --ipc bash -c "ip link set lo up; source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=77 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST; cd /mnt/c/Users/PC/Documents/odid编译/wksim; python3 -B tools/benchmark_joint_executor.py --output <新文件.json>"'
```

rclpy 版本与基准源码 SHA256 在证据 JSON 元数据。资源已释放（进程退出，无残留节点）。
