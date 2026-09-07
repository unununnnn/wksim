# 独立默认入口与原生 RGB 整合

2026-09-07。用户批准的 #9 环境/RGB 合同已执行到真实地面采集链路；两套独立候选提升为工作台 mission 默认。G0–G6/Full 仍未完成，原 Wayfinder 父图未改动。

## 已验证的产品行为

- PX4、ArduCopter 的正式独立入口均完成三航点公共任务、独立物理窗口和正常降落。每例 8 个公共请求、6 个原生 ACK；位置流的公共受理与物理完成分别核对，不虚构逐航点原生 ACK。五类进程的同时期映射和四个实验进程组退场已记录。`independent-admission-20260907/flight-audit.json` 绑定原始结果及每例 21 个源码文件；准入明确区分历史构建飞行证据与后来修改的准入代码。
- 默认配置选择 `independent_quad_dds_v1`、固定自主模型及独立飞控构建；旧配置保存在 `*-mission-retained-baseline.json`。资源/源码/消息覆盖检查保持严格。工作台预检原来仍装载旧 ROS 覆盖层，真实 MATLAB 首轮在预检拒绝且未创建飞行；现在复用正式入口的固定覆盖顺序。
- 新默认 PX4 的真实 MATLAB 六航点、暂停/继续、退出后自主飞行及只读重连通过；退出后的独立物理推进 63.14s。ArduCopter 同样通过，驱动确认的持续空中窗口推进 67.52s，并取得新版 UE 实时画面。扩大到完整退出后观察集的离线审计覆盖 72.24s；它不是把墙钟改成物理时间。两次私有 startup 校验均通过。
- UE 原生 RGB 使用 SceneCapture2D、GPU 异步读回及独立 PNG/JSON 保存，配置传感器/载具、安装位姿、尺寸和 FOV。仅在两个可见载具都属于同一已提交权威步时采集；旧 epoch、部分/过期状态使待交付图像失效。图像只通过新的通知交付，不扫描目录重放。
- 真实双飞控地面 `joint-rgb-20260907-run2` 生成 35 张 640×480 PNG，消费者接收并解码 15 张。每张对应两模型原始真值、权威时钟记录、实际相机位姿与声明的 K。消费者关闭 3.0404s，物理推进 1,556 个 1ms 步；重连首帧 3408，高于重连时 3148。正式停止及全部核心实验组清理通过。记录了实际加载 UE DLL SHA256 `eb917b4a5f794f22a1788016b932e11989095cf3bc98248a7112840cfe171022`。

## 命令与证据

以下命令在 wksim 根目录执行；WSL 命令使用 Ubuntu-22.04/root 和私有仿真命名空间。全部原始运行目录、命令行、固件/模型/源哈希及失败样本保留在 validation，未发布厂商资源。

```text
python tools/audit_independent_profile.py validation/independent-mission-px4-20260907-run1 validation/independent-mission-ap-20260907-run1 --source-archive validation/independent-admission-20260907/flown-source --output validation/independent-admission-20260907/flight-audit.json
tools/build-ue55.ps1 -Stage E:/ue5.5/build/wksim-native-rgb-20260907-b
python tools/validate_joint_rgb.py --manifest validation/ue55-build-f7800f1d24e84689bc538fd54800e74f/candidate-manifest.json --output validation/joint-rgb-20260907-run2
python tools/audit_joint_rgb.py validation/joint-rgb-20260907-run2 --output validation/joint-rgb-20260907-run2/audit-physical-final.json
python tools/validate_matlab_flight.py --stack px4 --output validation/matlab-independent-px4-20260907-run2
python tools/validate_matlab_flight.py --stack arducopter --view --output validation/matlab-independent-ap-20260907-run1
python tools/audit_matlab_flight.py validation/matlab-independent-px4-20260907-run2 validation/matlab-independent-ap-20260907-run1 --output validation/independent-default-matlab-audit-20260907.json
```

MATLAB 审计为当前实际依赖源码模式，双例通过。独立三航点历史证据显式使用保留源码模式，不将修改后的准入代码伪装成当时执行的代码。相机不是桌面截图；验证 PNG、位姿及原始模型记录的篡改副本均被审计拒绝。

## 失败、回归和仍未完成的边界

RGB run1 为失败：主机与仿真命名空间都看不到状态 socket，而 relay 进程仍存活；同一 WSL 启动期间 systemd-tmpfiles 的 /tmp 清理有记录。显示准备现放在 UE 初始化后，等待主机启动稳定再创建 socket；relay 丢失自己的路径时明确报错，不永久返回空状态或替换另一个所有者。run2 通过，真实删除/替换自己测试 socket 的负向检查通过。这不证明此前所有显示失败都有同一原因。

未经环境准备直接运行全库 unittest 曾失败，包含 ROS 包/Windows 路径环境错误，以及两条仍假定旧默认配置的断言。修正配置期望、明确 Windows 图像审计宿主，并按项目原有矩阵重跑：默认 399 项（36 跳过）、旧预检 11 项、安装候选 79 项、Windows 产品 104 项通过。日志为 `session-product-checks-NgtQWE0O`、`joint-control-checks-8XFUgRLl` 和 `migration-resume-20260907/windows-product-final.log`。Windows CRLF 按实际文件格式检查；完整暂存源码检查另允许已保留的 EOF 空行，并排除统一补丁格式本身必需的上下文空白。原始检查失败日志和最终源码检查均保留，未改变飞行/数值门槛或原实际源码字节。

本次 RGB 仅地面接入验收。已知几何/遮挡投影标定、空中图像流程、实际冷重置旧帧隔离、场景配置哈希统一、碰撞及必需动态环境反馈过期尚待实现/验证；#30 保持 open。现有城市建筑仍是视觉装饰。联合 0.5× 当前完整长窗及 1× 性能、浏览器/QGC/键盘实际操作、DLL ABI、正式数值参考/预算、硬件与其余 Full 项仍开放。没有增加任何事后数值容差。

22 个代理实际会话配置已核验为 gpt-6-astra/low，无嵌套；真实 FC/UE/MATLAB 串行使用资源，主代理检查改动、集成与原始证据。只结束本任务创建的进程，不操作真实硬件，不推送父级混合工作区。


最终残留实读：24 条 Windows 记录 PID 中原 MATLAB launcher 21652 已被 python.exe 复用，未操作该新进程；其余所选 PID 不存在。Linux 10 个不同的本轮实验进程组均为空。记录位于 `migration-resume-20260907/current-integration-{process-selection,windows-processes,linux-groups}.json`，与各运行同时期退出记录分别保留。
