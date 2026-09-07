# 2026-09-08 受控 QGC 构建与验证报告（#42 进展，不关闭）

承接 `ab6653f`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。Goal active；未关闭任何 G2/Full 门槛。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| WksimGCS 定制构建 | **通过**（Qt 6.11.1 msvc2022_64，VS2022，Release） | `work/qgc-contained-build/Release/WksimGCS.exe`（stage 含全部 Qt 运行时） |
| 构建身份 | 应用/组织/包名独立（WksimGCS/WksimLocal/local.wksim.gcs）；串口编译期去除；测试/安装器/GStreamer 关闭 | cmake 选项入档（下节命令） |
| 设置身份实证 | 实际设置文件为 `%APPDATA%/WksimLocal/WksimGCS Daily.ini`（daily 版命名，删除后由原程序重建证实） | 删除-重建实验 |
| 自动连接抑制 | 六个自动连接键全 false 后启动零自动连接（无 14550 默认链路、无 ZeroConf 链路）；读回无改写 | ini 读回 + netstat |
| 单一保存链路 | UDP listen **0.0.0.0:14560** 真实绑定（`type=0`，NO_SERIAL 构建枚举修正）；14550 经核实为本机既有 MissionPlanner 进程（非本轮，未触碰） | netstat（进程 PID 对照） |
| 遥测 GCS 转发（WSL 侧） | Observer 字节一致转发（钉定 FC 对端后）+ 反向 QGC 桥（钉定 GCS 心跳后字节一致到 FC）；17 项遥测测试通过 | `Simulator/wksim_runtime/telemetry.py`、`validation/test_wksim_telemetry.py` |

## 构建命令（可复现）

```
cmake -S ../qgroundcontrol -B work/qgc-contained-build -G "Visual Studio 17 2022" -A x64 \
  -DCMAKE_PREFIX_PATH=C:/Qt/6.11.1/msvc2022_64 \
  -DQGC_APP_NAME=WksimGCS -DQGC_ORG_NAME=WksimLocal -DQGC_PACKAGE_NAME=local.wksim.gcs \
  -DQGC_NO_SERIAL_LINK=ON -DQGC_BUILD_TESTING=OFF -DQGC_BUILD_INSTALLER=OFF -DQGC_ENABLE_WERROR=OFF \
  -DQGC_ENABLE_GST_VIDEOSTREAMING=OFF
cmake --build work/qgc-contained-build --config Release --target WksimGCS --parallel
cmake --install work/qgc-contained-build --config Release --prefix <abs>/stage
```

环境修补记录（全部本机、未改厂商安装）：QGC 源码最低 Qt 6.11.0、钉住 6.11.1；6.11.0 编译存在 `qHash<QGeoTileSpec>` 不兼容；缺失 Qt 模块（Graphs/HttpServer/Location/Sensors/TextToSpeech/StateMachine/Connectivity 及 6.11.1 全套）经 Qt MaintenanceTool（先自更新）安装；QGC `.venv` 重建 + pip 镜像（pypi.org TLS 不通）；mavlink 依赖按构建自定义命令预装；GStreamer 按范围关闭（#42 不需要视频流）。

## 拓扑发现（决定遥测接入设计）

实验私有网络命名空间（unshare）内 Observer 的 `127.0.0.1` 与 Windows QGC 的 `127.0.0.1` 不可达；显示链路的既有模式是「实验→/tmp UNIX 数据报（跨命名空间共享 inode）→WSL 默认命名空间中继→Windows」。遥测 GCS 桥必须走同一拓扑：**Observer 把钉定后的原始 MAVLink 经 telemetry_socket 交付，Windows 侧桥接助手在 127.0.0.1:14560（QGC listen）与 127.0.0.1:14570（QGC 会话目标）之间穿梭**。本 rounds 的 WSL 侧 127.0.0.1 设计已按此修正为承接口（config `gcs_udp_forward` 校验/转发/反向钉定与 17 项单测保留），Windows 桥接助手为下一步实施项。

## 失败与边界样本（保留）

- 两次错误设置路径播种（`WksimGCS.ini` 与扁平 `[Link0]`）均未生效且未误写，原文件保留。
- `type=1` 在 NO_SERIAL 构建下创建 TCP 链路的样本（枚举修正为 0 后正确绑定）。
- QGC 设置残留边界：QGC 学习任意来报发送者为会话目标（UDPLink.cc:476）；本机 MissionPlanner 持有 14550（既有用户进程，本轮未触碰）。QGC 心跳仅去 127.0.0.1 配置目标；外网到 14560 的伪造 MAVLink 发送者可成为 QGC 会话目标（接收侧边界记录；如需防火墙加固属主机配置，须另行授权）。

## 剩余 #42 前沿

1. Windows GCS 桥接助手（telemetry_socket ↔ QGC loopback）+ 双向真实联测。
2. 验收运行：真实实验 + 桥 + QGC 遥测互证（QGC 日志/截屏），随后**用户亲手在 QGC 界面切走任务模式**（GUI 输入自动化不可用为既有边界），驱动与审计核验任务撤销/不抢回/新请求。

#42/#32/#31/#21/#20/#6/1×/G2/Full 保持 open；未放宽任何阈值，未推送厂商资源。
