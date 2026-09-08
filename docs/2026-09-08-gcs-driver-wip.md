# 2026-09-08 受控 GCS 实跑驱动（尚未执行）

`tools/validate_contained_gcs.py` 由已核验 `gpt-6-astra` / `low` 的子代理实现，仅完成离线语法与设置准入检查。本次没有启动 WSL、QGC、SITL，也没有占用 UDP 端口。

在 `C:\Users\PC\Documents\odid编译\wksim` 使用 Windows Python，先保证其他正式实验已结束，串行运行：

```powershell
python -B tools/validate_contained_gcs.py --stack px4
python -B tools/validate_contained_gcs.py --stack px4 --execute
python -B tools/validate_contained_gcs.py --stack arducopter --execute
```

默认只执行预检（包括短暂独占 UDP 端口探测），`--execute` 才启动真实资源。每次默认产生新的 `validation/gcs-bridge-20260908/live-<uuid>`。发现已有 WksimGCS / QGroundControl 或端口占用即停止；不修改现有 ini，不杀已有进程。

驱动从示例复制正式 independent promotion 配置，用 joint profile 的 setup_files 启动现有 `validate_independent_profile.py`。WSL 私有 0700 目录里的诊断原始数据、Windows 桥原始数据、原生 observer 计数、QGC 载具身份日志、正式任务证据和进程身份均保留。物理真值只读 32 KiB 尾部，首次发现 run 路径后缓存。飞行高度超过 0.5 m 且已有真实反向提交后停止桥，随后要求仿真时间继续至少 1 秒，并由正式验证器证明正常落地、退出及进程回收。

QGC 官方本地源码 `src/Utilities/QGCCommandLineParser.cc` 表明 `--log-output` 是无参数 console 开关；实际类别来自 `src/Comms/LinkManager.cc` 与 `src/Vehicle/MultiVehicleManager.cc`，故使用 `--logging:Comms.LinkManager,Vehicle.MultiVehicleManager --log-output`。

正向原始字节必须在 native capture 中找到完整相同数据报。反向只计桥记录中 relay.reverse_forwarded 真正增长的数据报，以四字节大端长度加原始数据累积 SHA256，和 Observer.report 的 `reverse_forwarded_sha256` 及 `reverse_forwarded` 对照。字段缺失为 partial（退出码 1），不伪称端到端字节已互证；计数或摘要不一致为失败，需审查是否为 observer 接受心跳前的合法丢弃。桥上的 `reverse` 数只是尝试数，不作成功证据。

清理使用本次 Popen 对象。Linux abort 先校验 validator PID/start_ticks/argv，再 SIGINT 让既有验证器回收它的 manager；验证器若超时仍不退出，记录 cleanup-incomplete 并保留资源供人工审查，不扩大终止范围。退出后再按 PID/start_ticks 检查本次 wrapper、validator、relay 是否仍存活。私有目录不递归删除，失败证据保留。

尚未验证：真实 QGC console 输出可捕获性、载具日志匹配、实际桥接延迟与正式飞行。默认文件版本仅记录 exe 版本/哈希，没有外部签名基线对照。用户亲手切模式未执行，驱动成功也不等于 #42 整体验收。离线检查命令：

```powershell
python -B validation/gcs-bridge-20260908/check_driver.py
```

该检查通过：安全配置准入，自动连接、外部目标和多链路被拒绝；不启动资源。
