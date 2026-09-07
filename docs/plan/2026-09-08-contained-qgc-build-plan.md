# 受控 QGC 定制构建具体方案（待 #42 授权后执行）

2026-09-08。本方案在 [核查与 HITL](../2026-09-07-qgc-vendor-evidence-and-hitl.md) 的授权答复后可直接执行；不修改厂商安装/系统设置/其他项目文件，全部构建产物在独立目录。

## 目标

从本机 `../qgroundcontrol/` 完整源码构建一个**可核验受控**的 QGC：独立设置身份、编译期去除串口、运行期关闭全部自动连接、单一回环 UDP 链路，用作 #42 的本机地面站。

## 已核实的本机条件

- 源码：现代 CMake 快照（`cmake_minimum_required 3.25`，Qt6，QGC_CUSTOM_DIR 覆盖机制，custom-example 模板）。
- 构建开关实读（`cmake/CustomOptions.cmake`）：`QGC_APP_NAME/QGC_ORG_NAME/QGC_PACKAGE_NAME`（身份→私有设置路径）、`QGC_NO_SERIAL_LINK`（编译期去串口）、`QGC_BUILD_TESTING/QGC_BUILD_INSTALLER`（裁剪）。
- 自动连接默认值实读（`src/Settings/AutoConnect.SettingsGroup.json`）：UDP/Pixhawk/SiK/RTK/LibrePilot/ZeroConf 全部默认 True；抑制键存在（组 `LinkManager`）。
- 工具链：`C:/Qt/6.8.3/msvc2022_64`、cmake 4.3.1、VS2022、`.ccache`（树内既有，二次构建应显著加速）。风险：QGC 对 cmake 上限版本的兼容性以首次配置输出为准，失败如实记录。
- CLI 实读（`src/Utilities/QGCCommandLineParser.cc`）：支持 `--logging:LinkManagerLog,MultiVehicleManagerLog`（冒号同参数）与 `--log-output`；无 --settings-file。

## 构建步骤（批准后）

```
cmake -S ../qgroundcontrol -B <repo>/work/qgc-contained-build -G "Visual Studio 17 2022" -A x64 ^
  -DCMAKE_PREFIX_PATH=C:/Qt/6.8.3/msvc2022_64 ^
  -DQGC_APP_NAME=WksimGCS -DQGC_ORG_NAME=WksimLocal -DQGC_PACKAGE_NAME=local.wksim.gcs ^
  -DQGC_NO_SERIAL_LINK=ON -DQGC_BUILD_TESTING=OFF -DQGC_BUILD_INSTALLER=OFF -DQGC_ENABLE_WERROR=OFF
cmake --build <repo>/work/qgc-contained-build --config Release --parallel
```

- 构建输入：源码树哈希清单、上述全部选项、cmake/编译器/Qt 版本入档。
- 不动源码：优先全部走 -D 选项；仅当运行期读回证明默认仍不达标时，才把最小源码级修改列入 QGC_CUSTOM_DIR 覆盖（改动逐行入档并随证据发布）。

## 运行期受控（首启前播种私有配置）

- 私有设置路径由身份决定（`%APPDATA%/WksimLocal/WksimGCS.ini` 或等价位置，首启前以只读方式核实实际路径再写入）。
- 播种内容（版本键与源码 `QGC_SETTINGS_VERSION=9` 对齐）：`[LinkManager]` 下 autoConnectUDP/Pixhawk/SiKRadio/RTKGPS/LibrePilot/ZeroConf 全部 false；单一保存链路指向本实验遥测出口的回环 UDP 端口；不播种任何串口/蓝牙/转发项。
- 首启验证（无 GUI 自动化）：
  1. 读回 ini：抑制键全部 false、无未预期 LinkConfigurations。
  2. `--logging:LinkManagerLog,MultiVehicleManagerLog --log-output` 的实际日志：仅回环端点、无自动连接创建、无设备枚举（串口已编译去除）。
  3. 进程 UDP 端点清单（Get-NetUDPEndpoint 按 PID）：仅 127.0.0.1 绑定/目标。
  4. 实验遥测只读接入后：QGC 日志出现载具 HEARTBEAT/身份（与实验原生记录互证），界面可见性由系统只读截屏存档。
- 失败即停止并保留证据；不以「没报错」代替受控证明。

## 验收分工（与 #42 票据对齐）

- 主代理：构建/播种/读回/日志/端点清单、实验遥测接入、任务撤销/不抢回/新请求的驱动与审计。
- 用户（HITL）：在 QGC 界面执行「切走任务模式」的实际点击（GUI 输入自动化不可用为既有边界），其余全部自动核验。

#42/#21/#20/#6/1× 的各自未决状态不变；本方案不预先宣称满足任何验收标准。
