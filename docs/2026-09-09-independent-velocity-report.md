# #32 双栈独立速度/偏航补充验证

2026-09-09。按原票的任务级范围补齐独立入口真实证据，未据此单独关闭#32。随后原始联合全场已完整通过及重复原始审计，最终结论见[收口报告](2026-09-09-velocity-yaw-closure-report.md)。旧联合失败、#20/G2的持续1×义务保留。

首次运行前的工况、误差界、采样余量与新增组合见[预先约定](2026-09-09-independent-velocity-plan.md)。复用正式runtime.run、已准入independent_quad_dds_v1和Task.execute_velocity_yaw，未改固件/控制包或绕过原生解锁与物理门。先执行实际[2,3,3] ENU位置基线，再进行惯性速度、零速、偏航速率、支持/拒绝的角度组合、机体系速度和回中，最后降落。

发现并修复独立3×时基错误：原速度任务dwell用FC boot时间，偏航积分期望却用墙钟。现在与dwell一致，联合仍用权威ROS时间、独立用FC boot时间；墙钟超时、0.35rad积分界均不变。真实Task方法的无I/O测试在旧代码下复现错误，修正后独立3×与共享ROS两路径通过。

## 双栈完整成功

| 物理窗口 | PX4 final04 | AP final01 | 原门槛 |
| --- | --- | --- | --- |
| 惯性速度最大逐轴误差 | 0.05427m/s，3.48s | 0.02291m/s，3.50s | ≤0.3m/s，≥3s |
| 惯性回中最大速度/漂移 | 0.06385m/s / 0.58197m，4.52s | 0.03810m/s / 0.61571m，4.46s | ≤0.25m/s / ≤1m，≥4s |
| yaw-rate积分最大误差 | 0.12595rad，4.56s | 0.14168rad，4.52s | ≤0.35rad，≥4s |
| 速度+yaw角 | 0.06740m/s / 0.03838rad，3.52s | 明确拒绝，后续2.44s最大速度0.01307m/s | PX4速度/角度界；AP精确拒绝与≥2s无副作用 |
| 机体系速度最大逐轴误差 | 0.05890m/s，3.52s | 0.02402m/s，3.48s | ≤0.3m/s，≥3s |
| 机体系回中最大速度/漂移 | 0.05329m/s / 0.62581m，4.52s | 0.03299m/s / 0.62577m，4.48s | ≤0.25m/s / ≤1m，≥4s |

每场13个真实公共请求。PX4额外角度回中也完整通过，保持4.50s、最大速度0.10330m/s/漂移0.05954m、角度误差0.00314rad；AP错误组合为command_id6，精确arducopter_velocity_requires_yaw_rate_mode，未更新为被接受的运动命令。两场位置基线、正常落地、safe_landing/children_reaped/cleanup_errors=[]通过；最终物理高度分别约-0.000001m/-0.000006m。

原始根：`/root/wksim-independent-velocity-px4-20260909-04` 和 `/root/wksim-independent-velocity-ap-20260909-01`。项目归档在validation/independent-velocity-20260909/{px4-final,ap-final}/，76个原始文件/源码绑定列于archive-manifest.json。不跟随FC工作目录别名复制资源。

独立审计使用真实约50Hz时间/物理游标，未伪装成联合1ms逐步日志或把独立PX4/uav1改成联合uav2。逐条重算世界/body_flu速度、真实NED→ENU偏航积分、漂移、原始公开请求/事件和资源身份。每个物理最低时间要求不变；预先安排的0.5s驻留余量用于覆盖采样边界，未扩大任何误差界。审计重复字节一致：PX4 SHA5ca7af58d5d6720d6ef372e40c12828eb7dfb11f26ee10030517a0e8436d7125，AP SHA6caa9bd0abbbcd0a6ce724f1d71d4a31dd3892e81eb37360238fdb38e3fcc025。

## 失败与准备段纠正

PX4 run01仅惯性/偏航速率探针pass，未冒称覆盖后增的body/角度工况。run02在角度回中固定2.5s之后观测速度0.265m/s而失败；run03第一次达到条件后再次越界（0.255m/s）而失败。run04将准备段改为最多12墙钟秒内连续满足原保持条件1.5个boot秒，条件失效清零准备计时；正式4.5s保持窗口仍任何违例立即失败。不修改控制律、飞控参数或误差界。各失败原始数据和执行驱动版本均保留。

## 命令与回归

在WSL Ubuntu-22.04 root、项目根使用新的run-id/输出根：

```sh
bash tools/run-independent-velocity.sh --config Simulator/wksim_runtime/examples/parameter-px4.json --run-id independent-velocity-px4-20260909-04 --output-root /root/wksim-independent-velocity-px4-20260909-04
bash tools/run-independent-velocity.sh --config Simulator/wksim_runtime/examples/parameter-arducopter.json --run-id independent-velocity-ap-20260909-01 --output-root /root/wksim-independent-velocity-ap-20260909-01
python3 -B tools/audit_independent_velocity.py /root/wksim-independent-velocity-px4-20260909-04
python3 -B tools/audit_independent_velocity.py /root/wksim-independent-velocity-ap-20260909-01
```

当前矩阵469项：440通过/29跳过，旧预检11通过（validation/session-product-checks-06FITPm9/）。新增实际Task时基、连续稳定准备、双栈原始审计及8类单字段篡改负例通过。8条本轮成功实验子进程记录均已回收，精确argv/cwd当前检查无匹配；不以裸PID存在判断历史身份。

这些证据支持#32全部声明组合的独立任务行为。联合速度全场另以原始0.5×流程复跑通过，历史rate_unmet不改写；持续1×、G6及Full其余范围继续保留，不能由独立3×运行代验。
