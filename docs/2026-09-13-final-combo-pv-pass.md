# #83 最终组合公共 P+V 兼容性通过

主会话实跑 `joint-public-flight-1w6dru32`（epoch `a160e99bb6ac46b4a09f0b36b3daeed7`），runner 与完整原始审计均 PASS。#82 已 CLOSED；本结果满足 #83 的限定切片，不完成 #84、#33 或 Full/G0–G6。

## 执行与证据身份

- Ubuntu-22.04 私有检出 `/root/wksim-release-acceptance-fe3`，执行提交 `95da8809b7af3c47e42457c6dea0cdb96c563407`。
- 原件：`validation/joint-public-flight-1w6dru32`；live：`/root/wksim-joint-flight-gx470_4a`。Windows 选取保留包：[pv-settle-1w6dru32](../validation/33-final-combo-luna/pv-settle-1w6dru32/bundle-manifest.json)。完整 DDS、wire、truth、原生源码和二进制留在 Linux；选取包不冒称完整独立审计输入。
- 命令逐字保留于包内 `launch.sh`：当前 AP mixed + Control c2IXOr + Message Rzj3Pf，`full_xyz_pv_yaw_v1`、async evidence、manager GC freeze，两项计时探针均关闭，无 early-work。外层与 runner 均 exit 0。
- AP manifest SHA `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`；Control `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e`；Message `29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219`。固定 PX4/model 保留原准入链。
- Control 的11份Python、15份Simulator支持、2份资产及构建/安装/消息封存经原 `check()` 完整核验。ZlTVa4已与当前8份支持源码不一致，因此新准入使用唯一当前c2身份，旧身份仅保留历史原件审计。
- Task执行源码 SHA `c6b3350eea83ff01a33c59a679801c223ada87284a090c4d21f45bdd01996132`；PV审计器 `920aab3cb52220229567e8a56d28adae69ea0adaa9ee45019b1f64c74b56423c`；mixed身份审计器 `f7f8816674f9526d48c808cfb10a31ca47fa7d08c6263ff531fb13edddb40234`。
- 完整审计文件 SHA `8140d80e5695bb377dedaef7198cb67811456a2429bab005085b2a5926f0e8c4`。主会话另核对 result SHA 与全部302项原始输入 SHA 一致。

## 原验收门结果

两栈分别执行两段12秒轨迹，每段12001个连续1ms参考样本；原位置≤0.5m、逐轴速度误差≤0.3m/s、yaw≤0.15rad、端点2s准备/2s保持、停止2s准备/4s保持、速度≤0.25m/s与漂移≤1m全部通过。第二段锚点、原始公共请求、实际原生目标、停止与LAND均通过独立原始审计。

| 两栈两段中的最大值 | 实测 |
| --- | ---: |
| 轨迹位置误差 | 0.120215 m |
| 逐轴速度误差 | 0.076676 m/s |
| yaw误差 | 0.039097 rad |
| 停止速度 | 0.040880 m/s |
| 停止漂移 | 0.091560 m |

单锚0.5×、1ms、4tick屏障、无追赶保持；最坏累计迟到89,299,145ns < 100,000,000ns。完整10s滑窗27493个，最大相对误差0.001305497 < 0.02；完整60s滑窗21245个，最大0.000513893 < 0.01。最终tick116004、stopped，wall283.260591381s。两栈task/model/control正常退出，控制关闭与async写入完整；自有PGID2060–2069独立确认全空，前后boot身份一致，源码与保留快照SHA一致。

## 真实失败及修正边界

旧诊断xtj8wk8i不改判：AP航点窗口最初两个毫秒速度0.505341/0.502214m/s超过原0.5上限。新任务仅以fresh估计速度≤0.4作为进入航点保持的余量，之后仍按原2秒与0.5门；没有裁掉原件前两个样本或缩短窗口。

新场第一份审计因PX4 `duplicate_source/status`失败，原报告保留。两条同system_id、同source_stamp的消息完整解码字段相同，符合mixed审计已存在的严格重复状态规则（原CDR字节并不完全相同，未声称字节相同）。PV审计复用该规则，仍绑定run/control epoch、错误级别、两包证据、完整字段、时间与系统身份，并在最终报告中显式列出1个已佐证重复事件。来自真实两包的异字段、单包、过期、会话错配、FATAL及回退时戳反例全部拒绝；不是通用ERROR豁免。

正式profile仍拒绝诊断运行，旧profile/promotion证据未改。#84还需要同组合mixed能力证明、精确映射和真实正式入口验证；加速度执行、yaw-rate、其它原生边界及G6零预算失败均不由本次结果代验。
