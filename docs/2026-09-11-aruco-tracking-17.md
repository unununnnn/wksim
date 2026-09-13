# 第17场及线程采样

PX4候选 `aruco-track-83ab77c0eb` / `ddcbd0ee3cf54c2cb77de4fecd5a0d6c` 在tick40296、累计迟到100.456794ms时失败，未起飞/启用RGB。运行器退出1、管理器退出0；采样器退出0。原件211文件、4分片，SHA256 `adc0c2b74611d7ad7440499cc131f369fe6ab46e2361ba0d436cf60a76244806`。

外部50Hz/40s采样在观测tick10140后启动，实际覆盖release起点10268..30240，1991批、123442线程行；日志SHA与result核对一致，run/epoch/boot_id一致。每批最大读取4.875ms，最大相邻采样间隔20.649ms，采样器线程CPU共4.747s（约40s观察窗口），有不可忽略的观察开销。当前schedstats关闭，因此没有拿runqueue零值作为调度结论。

该窗口监督器所有被观察线程CPU增量约19.919s，AP约2.245s，PX4约1.771s；多线程计数并非单核利用率。窗口内记录release累计增量40.686ms，其中tick18720事件约11.973ms；相邻约20ms采样段监督器CPU13.758ms、AP1.227ms、PX41.485ms。时间重叠不能证明因果，也不区分宿主抢占与全部客体记账影响。该探针没有覆盖最终40296失败瞬间。

已有核心阶段探针仍留有未覆盖的监督器循环耗时，包括物理步骤间的管理路径与`/clock`发布。下一步只在既有CPU诊断模式下记录这些边界，不改变执行顺序或倍率预算，不再依同样条件盲目重跑。

采样原件在 `validation/joint-thread-probe-17`；分析为 `validation/coordination/aruco-17-{thread-analysis,rate-replay,peak-timing}.json`。600s自有WSL保活进程74832已退出0；boot_id固定为`87e04105-21a5-41fd-a4ea-11f182fe8eb7`的这一场仍失败，因此不宣称保活解决了倍率问题。当前所有本场运行与采样句柄均已终态。
