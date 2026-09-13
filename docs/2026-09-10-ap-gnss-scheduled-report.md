# AP GNSS 延后计划与原生恢复验证

2026-09-10，承接 #109/#121。此前 AP 候选固定 `[4000,6000)`，无法在真实初始化/悬停后安排故障。本批新增独立候选，保留旧候选与原始证据。

## 已实现并验证

- `tools/ap_gnss_flight/SIM_WksimGNSS.h`：每个 JSON 仍带严格 run/epoch/vehicle/tick 前缀；允许启动后独占提交一次规范 `gnss_plan`，提前至少 1000 tick，固定停止新 GPS 15000 tick，完整运行上限180000 tick。计划改写、消失、非规范编码、迟到均失败。
- GPS 驱动 4 秒无消息会重新探测，固定 AP_GPS.cpp 的 `GPS_TIMEOUT_MS=4000` 已实读。候选显式记录每个新传感器代次、出生 tick 和一次空历史预热；新代拒绝出生前的非零旧来源。计划后仅在有限的故障/恢复阶段允许重新创建，不通过改时间戳包装旧数据。
- 真实 AP 进程执行了两次80000-tick静止地面测试。计划于45000提交，在 `[50000,65000)` 实际抑制原生 GPS 模拟串口写入。原生400个样本、2702个UBX包（含被抑制候选），抑制字节27690；故障窗实际写入为0，恢复后实际写入31950字节。
- 加入只读 DDS 观察的第二次运行，记录3371条真实 WksimState。GPS质量于原生53.795s失效，66.456s恢复有效定位；数据链持续工作，期间 position_valid 也确实转为false。原始CDR重新解码一致，未解锁或飞行。
- 主GPS经历14代（第二GPS只创建、未输出数据），说明不能把真实驱动重探测当作原对象的连续历史。全部代次/源时间/模拟HAL相位和UBX校验已独立审计。
- Control的 COMMAND_CONTROL 在原生定位无效时先撤权并停止缓存位置输出，避免落入通用参考量回退逻辑。51项控制/场景/原生适配回归通过。
- 10个C++计划/时钟/代次边界用例和真实原件/计划篡改/UBX篡改审计测试通过。资源句柄在失败审计时同样关闭。

## 候选身份

- AP根：`/root/wksim-ap-gnss-flight-20260910-01`
- 固件 SHA256：`ef16ad88ed01f55b7e07bcd0b82cbe681fab392cac76649f6cd941ed141f34a7`
- `flight-seal.json` SHA256：`c567520ea2204afdc1e9f4eae5fa3fe3782ede825d476517c8a459aab2ed0517`
- 完整24594个源文件核验，相对固定基线只改变 `SIM_JSON.cpp`、`SIM_GPS.cpp`、`SIM_WksimGNSS.h`。DDS生成产物与构建日志另行封存。
- 新Control：`/root/wksim-joint-control-hy8WVw/build.json`，SHA256 `151389198b8719ff443db41cd24260d75f239c6d5fe016399589818231698f2a`。

原件与验证记录在 `validation/45-gnss-scheduled-20260910/`，压缩归档后逐项读回核验SHA。厂商/飞控源保留本机候选目录，归档只包含构建身份、日志和本次数据。

## 可执行入口与未完成项

```sh
python3 -B tools/build_ap_gnss_flight.py /root/wksim-ap-gnss-flight-NEW
python3 -B tools/seal_ap_gnss_flight.py /root/wksim-ap-gnss-flight-NEW
python3 -B -m unittest validation.test_ap_gnss_schedule -v
WKSIM_GNSS_SCHEDULE_AUDIT=1 python3 -B -m unittest validation.test_ap_gnss_scheduled_audit -v
```

地面传感器入口是 `probe_ap_gnss_schedule.py`，可选只读DDS入口是 `probe_ap_gnss_dds.py`；均要求新输出目录和私有网络命名空间。对应完整命令与环境存于证据目录。

本批不是 #45 飞行验收。`gnss_task.py`、双栈飞行配置/运行器、完整飞行审计及 #111/#112 真实飞行仍未完成。下一步须结合本次原生GPS失效证据、默认failsafe参数与不自动重放原则，冻结故障飞行工况，再验证撤权、实际飞控动作、新鲜恢复、显式新接管和降落。原 #22 仅覆盖 Agent 链路的边界不扩写；R1、RateUnmet、G6/Full 不改判。
