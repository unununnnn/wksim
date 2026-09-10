# 双栈 GNSS 中断与显式恢复：整场验收

2026-09-10。已交付真实模型运行器、冻结GNSS工况、原始传感器/状态/物理审计，最终 PX4 与 ArduCopter 两场通过。任务先完成三米稳定悬停，在真实传感器链停止新GPS15秒；定位失效时撤销任务，恢复后使用新请求完成不同航点与降落。没有把 Agent 断流、显示标志变化或地面夹具当作本次飞行。

| 项目 | PX4 | ArduCopter |
| --- | --- | --- |
| 最终运行 | `d1d4028e65da402f918eef2ec768d8bb` | `005a06b9bf0b44098ba03698a167f2fe` |
| 物理1ms记录 | 69,244步 | 104,871步 |
| 实际故障边界 | 150个GPS发送候选被抑制，原始IMU/真值继续 | 原生模拟串口抑制27,690字节UBX，恢复后实际写入61,344字节 |
| 定位/任务 | 活跃数据链上定位无效，Control撤权 | 活跃数据链上GPS/定位无效，Control撤权 |
| 失效动作 | ULog确认 `COM_OBL_RC_ACT=4`，实际LAND | 撤权后显式LAND，原生确认 |
| 恢复 | 新鲜定位、无自动重发、新解锁/接管/航点 | 同左，并处理重解锁导致的home变化 |
| 最大包线距离 | 3.3143m | 3.6408m |
| 最终结论 | PASS | PASS |

[最终统一审计](../validation/45-gnss-flight/final-matrix.json)绑定每场run/scene/control epoch、原件及源码SHA。所有物理步满足冻结的4m/15度/4.5m包线，起点前6000步和新目标最后2000步满足0.3m/0.3m/s/0.15rad门槛。故障窗原始传感器质量/源时间保留，旧GPS数据不被重打时间戳。审计独立重解码MAVLink/UBX/CDR，检查撤权后到新请求前无位置输出，最终实际落地上锁。

## 实现与可复制入口

- `tools/run-gnss-flight.sh` / `run_gnss_flight.py`：独立net/ipc/mount、资源准入、源码/安装/进程记录、完整终态与清理。
- `gnss_physics.py`：每1ms真实模型和原始actuator记录；物理所有者接受不可变请求、选择未来整数起点；PX4调用既有真实HIL_GPS门，AP保留完整JSON真值并附权威身份/计划，故障发生在原生GPS串口输出。
- `gnss_task.py`：不把定位失效当成数据链断开；等待真实新鲜导航后发新请求。AP重新解锁会改home，恢复点通过原生home经纬高变化映射，物理真值不参与控制。恢复参考以0.3m/s渐变，最终物理目标仍为原定 `[3,2,3]`。
- `audit_gnss_flight.py`：原始包、实际参数、原生模式、物理逐步与新请求独立审计；`test_gnss_audit.py`拒绝预算修改、中断窗发包及缺失新恢复命令。

当前冻结入口为 `gnss-flight-v3.json`。两栈最终 Control 候选为 `/root/wksim-joint-control-zt3KMT/build.json`，SHA256 `14a006967885ac91be3fd67be883eb1df1016b13110eea31e7f3fd5f3a73750a`。AP固件及完整源码seal沿用上一批 `ap-gnss-flight-20260910-01`；未改其传感器抑制方程或旧候选。

```sh
bash tools/run-gnss-flight.sh --help
bash tools/run-gnss-flight.sh --stack px4 --run-id <新的32位hex> --preflight \
  --control-manifest /root/wksim-joint-control-zt3KMT/build.json \
  --control-sha256 14a006967885ac91be3fd67be883eb1df1016b13110eea31e7f3fd5f3a73750a
# 运行时去掉 --preflight，并提供一个新的 /root/wksim-gnss-flight-* output-root。
python3 -B tools/audit_gnss_flight.py <run-directory> --output <新的外部audit.json>
```

运行与审计需载入记录的ROS消息覆盖层。实际两栈只读预检、唯一运行ID和准确路径在证据目录；模板中的占位内容不是已执行命令。

## 失败保留与修复

1. v1 PX4默认Position→Return失效链向home移动并越出4m，保持失败。v2明确配置原生Offboard-loss LAND，原包线和15秒故障不变。
2. 一次恢复观察订错GPS主题；按固定源修正为`vehicle_gps_position`，解锁前加入观察通道就绪，真实DDS测试通过。
3. AP只等原生EKF动作时漂移越界；v3在已观察到撤权后发显式LAND并核验确认，包线不变。
4. AP重新解锁的home变更需要参考系转换；保留旧失败后按原生经纬高转换，目标未改变。
5. 大位置阶跃超倾角；改为有界参考渐变，未增大倾角限值。
6. NumPy标量导致一次阶段/结果序列化失败；原目录保留不完整失败说明，确认当前无该命名空间进程，转换后整场重跑。该次没有伪造正常result。

51项控制回归通过，GNSS输入/发包/计划/坐标/数值序列化及真实观察器测试通过，最终实际飞行与审计负例分别保存。原始失败和其v1/v2配置都保留。

本批是显式实验候选验收，不提升默认生产配置，不关闭G6/Full或联合倍率问题；全球航点完整合同、规划/相机、ABI与硬件模式仍另行推进。
