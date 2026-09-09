# #109 AP 权威 tick 原生 GNSS 中断候选

本票交付独立 ArduCopter SITL 候选与地面原生传感器验证。固定地面 JSON 真值是明确标记的输入夹具；原生 GPS 生成、UBX 编码、SerialDevice 写入和拒绝退出来自真实 ArduCopter 进程。这里没有解锁、飞行、EKF 恢复、任务撤销或任务重新接管验收。#45 的原 AC 与依赖仍由父票检查。

## 归属与版本

仓库写入只在本文与 `validation/45-ap-gnss-candidate/`。候选源在新的 `/root/wksim-ap-gnss-109-20260909-05/src`，构建在同根 `build/`；封存源 `/root/wksim-ap-clock-stop-OXQqdR/src` 保持只读。基线 Git 提交为 `1511f27194f1dcc3728270883047bdf022b3fd53`，已包含 DDS/外部控制及整数 JSON 时钟/可中断退出补丁，不称 pristine upstream。

候选修改原生 `libraries/SITL/SIM_JSON.cpp`、`libraries/SITL/SIM_GPS.cpp`，新增 `libraries/SITL/SIM_WksimGNSS.h`。这些均位于隔离复制品中；仓库只保存生成器、候选头文件及生成的证据补丁。`build.py` 检查封存 JSON/GPS/UBLOX SHA，要求新目录，执行唯一锚点替换，保留构建日志及二进制 SHA。`archive.py` 对封存 manifest 所列源码逐项核对，另记 symlink、继承修改的完整 Git diff、编译器身份及新增头文件身份。库存范围不是所有构建环境的证明，外部 DDS 生成器路径仍在准确构建命令中。

## 权威身份和时间合同

每个完整 JSON 的首字段必须为 `"wksim":"<32位小写十六进制run>:<32位epoch>:1:<tick>"`，并使用 `probe.py` 的规范化编码。run/epoch 从新进程环境 `WKSIM_RUN/WKSIM_EPOCH` 冻结，首次 tick=1，之后严格加一，上限 60000；不接受重复、回退、缺 tick、错对象或跨 epoch 复用。重启必须创建新进程、新输出目录及新身份。仅支持隔离命名空间内由单一受控发送者提供的 loopback JSON；没有密码学认证，也不是任意网络 JSON 的通用解析器。

同一 JSON 中 `timestamp * 1e6` 必须与 `tick * 1000` 相差不超过 0.0001 微秒；禁止 no_lockstep/no_time_sync。原始 JSON 在校验前写入 `JSON` 行，全部字节以 hex 保存。原生字段解析继续走现有 SIM_JSON；position、IMU、velocity、quaternion 均完整保留。

实读 `_fdm_input_local` 发现顺序是 `update_model → fill_fdm → sim_update(GPS) → stop_clock`。因此 GPS 更新处 `_sitl->state.timestamp_us` 已到当前模型 tick，而 AP_HAL 时间仍是前一个 tick。候选用 `model_ms(state.timestamp_us)` 校验身份时间并调度 GPS 生成/采集；不调整全局 HAL 调度。每个 SAMPLE 同时保存当前权威 tick 和实测 HAL 微秒，并要求已冻结的 `(tick-1)*1000` 相位。该要求只对本隔离 JSON 候选成立。

`GPS_Data.timestamp_ms` 在 `interpolate_data()` 返回时保留较老插值端点的时间，并不等于“当前 tick 减配置延迟”。候选保留其原值和完整 GPS_Data 质量/位置/速度/姿态/精度字段，要求同一原生传感器代次内源时间严格增加、非未来、年龄不超过 500ms。500ms 是本地传感器证据预算，不改变任何物理、实时倍率或父票合同。5Hz 生成对齐权威 tick 的 200ms 整数网格，避免 backend 创建时间决定传感器相位。

`SITL_State_common.cpp` 的串口工厂在打开模拟 GPS 时新建 `GPS` 对象；真实启动中会再次创建，不能把该对象的新历史当成旧对象的连续历史。候选在 `GPS` 构造处记录 `GENERATION`（tick/instance/递增代次），清空该代来源游标和新鲜许可，SAMPLE/WRITE 均附代次。只允许计划开始前出现这种显式启动重建；在 tick>=4000 构造立即退出109。每代仅允许一次零历史 WARMUP 且不发布；同代重复空历史、计划开始后空历史、后续过期或倒退均退出。这是本地传感器代次，不能冒充 run/控制 epoch 的热恢复。

UBX 周时间继续来自原 `gps_time()`，包含 HAL 相位及原有 200ms 量化；候选没有改写 UBX 时间来包装旧坐标。审计解码原包 TOW，并与 GPS_Data 的旧端点时间分别列出。

## 实际写入与故障边界

本候选冻结单载具、主 GPS UBLOX、5Hz、100ms 配置延迟，第二 GPS 不分配 backend；最终计划为 `[4000,6000)` 权威 1ms tick。早期 `[2000,4000)` 候选失败记录保留，最终运行前重新冻结启动观察段，不回写旧数据。计划在进程启动前由候选源固定，manifest 同时记录，不支持运行中替换计划。

最终地面参数另冻结 `GPS1_TYPE=2`、`GPS_AUTO_CONFIG=0`、`GPS_DRV_OPTIONS=4`。实读 AP_GPS.cpp 的探测条件：选项 bit2 允许115200的UBLOX检测；默认自动探测在4s后仍反复重开串口，已触发候选代次保护。最终参数让原生探测在故障前稳定，既没有关闭代次保护，也没有改写该失败记录。每次运行的完整参数文件、SHA及原生启动命令均在 manifest 中。

GPS 继续生成并编码候选 UBX 数据。在 `GPS::write_to_autopilot` 边界，计划内记录完整拟写入片段并返回 0，完全不调用 SerialDevice 写入；计划外调用真实 SerialDevice 并记录返回字节数。新鲜度未受理、错误 GPS 配置、短写或写失败均闭环退出109。串口片段包括 UBX header、payload、checksum；审计按 tick/instance 拼接、检查长度和校验和，并验证每次计划内返回0、计划外完整写入。

这里的实际写入指原生模拟串口 ByteBuffer 接受字节，不等于 AP GPS 驱动已消费、定位有效或飞行恢复。信号中断、原始无fix质量、过期/重放拒绝分别保留；恢复只允许之后的新采集样本，没有缓存重放。

## 入口与复查

在 wksim 根、WSL Ubuntu-22.04 执行，使用新的唯一输出目录；已封存目录不能再次作为输出。

```bash
python3 validation/45-ap-gnss-candidate/build.py /root/wksim-ap-gnss-109-20260909-05
python3 validation/45-ap-gnss-candidate/check.py /root/wksim-ap-gnss-109-tests-04
unshare --net --ipc --mount --propagation private bash -c 'ip link set lo up && mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm && exec python3 validation/45-ap-gnss-candidate/probe.py /root/wksim-ap-gnss-109-20260909-05 /root/wksim-ap-gnss-109-ground-05'
```

`probe.py --fault run|epoch|duplicate|timestamp` 在 tick 1001 注入相应错误；每个负例用独立原生进程/身份/命名空间/目录。无ROS/UE启动，90s墙钟上限，只终止本入口保存的子进程句柄，并记录退出码、PID、boot_id、proc stat、实际 argv。正常完成依据 8000 个原始 JSON 与下一 servo 请求确认，随后 TERM 并等待；超时强杀明确判失败。

`check.py` 的 C++ 逻辑夹具覆盖 3999/4000/5999/6000、源年龄边界、一次预热及重复空历史拒绝、真值tick错配、未来、过期、重放、HAL相位、不带新鲜样本的写入以及短写。这类结果与 `probe.py` 的真实原生过程分开保存。原生审计比对发送/接收完整 JSON 字节，检查身份、连续时间、真值完整、逐段返回值和 UBX 校验；不会仅凭进程退出0认定通过。

最终结果、失败历史和归档索引见 `validation/45-ap-gnss-candidate/summary.md`。源码/构建/运行只证明本票原生候选范围；实飞接入与独立整场审计留给 #121/#112。
