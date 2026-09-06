# MATLAB 最小接口边界

2026-09-05。**已确认传输：基础MATLAB `tcpclient` + JSON，可选桥接ROS2**；不要求ROS Toolbox或Instrument Control Toolbox参与此路径。MATLAB原生ROS2直连延后到本机R2022b/Humble联测之后。本地说明从属于 [MATLAB 最小接口边界决策](https://github.com/unununnnn/wksim/issues/5)，该决策仍开放。

待用户回答的范围问题是：首期是否只读取状态/日志、配置实验参数、发送Prometheus高层命令，不承担物理步进、飞控保活或必需启动流程；完整模型联调与故障注入后续扩展。传输方式的确认**没有自动确认这一功能清单**。以下协议细节为实施草案，不声称已构建或联测MATLAB桥。

## 本机依据

本机 `D:/matlab/install date/VersionInfo.xml` 标记R2022b、`9.13.0.2049777`。ROS Toolbox本地Contents标记1.6/R2022b；基础MATLAB目录可见 `networklib/tcpclient.m` 和JSON编码/解码文件。安装元数据和文件存在不等于可用许可证，本阶段未启动MATLAB或执行许可检出。

MathWorks官方表将R2022a–R2023a的ROS2支持基线列为Foxy，R2023b–R2024b列为Humble；官方也允许消息定义相同的跨发行版通信。因此不能直接把本机R2022b判为“不兼容Humble”，也不能把同名消息当作已验证。见[ROS系统要求](https://www.mathworks.com/help/ros/gs/ros-system-requirements.html)。`tcpclient`属于[基础MATLAB TCP接口](https://www.mathworks.com/help/matlab/ref/tcpclient.html)，与[Instrument Control Toolbox的udpport](https://www.mathworks.com/help/instrument/udpport.html)分开考虑。

本地RflySim的 `RflySimSDK/simulink/RflySendUE4CMD.m` 使用旧 `udp` 向广播20010端口发送52字节命令加int32标记，没有请求关联或应用层确认。本地SDK仍可作为行为/字段来源，但此脚本不能直接替代新的请求、状态、超时契约；不修改其原文件。SDK中的Simulink/MEX示例也不证明基础MATLAB客户端能独立运行。

已核对文件SHA256：VersionInfo.xml为 `54c0f2f45b629d1861aaf6e572b06d109df7d833520466af7dd544f89b22dc72`；RflySendUE4CMD.m为 `d0dd1d1e5a54fc32c574d32769861296e07d4cd50b3717fc6c11d0f0c42b1b3c`。不复制这些安装文件到目标仓库。

## 拟实施的最小通信契约

- 采用UTF-8逐行JSON，明确版本、运行实例和请求ID；帧长与缓冲上限受限，拒绝非法JSON、非有限数值、未知方法及越界字段。TCP连接成功、请求受理、飞控确认、任务完成分别报告。
- 复用Prometheus字段和枚举，说明ENU/FLU、米/秒/弧度以及全局经纬度单位；不另造一套四旋翼控制语言。飞控不支持的命令显式拒绝。
- 状态携带权威仿真时间和状态年龄；超时检测使用墙钟。MATLAB断开不影响物理步进、飞控保活或UE；重新连接只读当前状态，不自动重放未确认的控制命令。
- 实验配置只允许明确白名单，不提供任意文件、shell、脚本或DLL执行入口；日志按运行实例读取有限片段，不把任意路径暴露给网络客户端。
- 桥在WSL按需启动，缺少MATLAB时主SITL照常运行。默认不暴露远程监听，不自动改防火墙；Windows/WSL地址按实际网络模式显式配置，不能假设两侧127.0.0.1天然互通。

端点名称、支持命令集合、报文字段和错误码随范围确认及首个客户端/桥实现一起冻结。先进行回环碎片/粘包、边界拒绝、超时/断开、不重放测试，再用本机MATLAB客户端联测；只有通过后才能宣称“本机MATLAB接口可用”。该轻量接口不取代后续完整模型联调，也不收缩Full CopterSim复刻目标。
