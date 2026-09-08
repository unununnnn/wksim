# #18 真实浏览器操作与双栈收口

2026-09-08。此前阻挡 #18 的浏览器环境已变化，本次内置浏览器可正常访问本机工作台。没有修改浏览器策略、证书或隔离设置。主代理通过 CUA 真实操作页面，后端继续调用正式 WSL 入口和原生 Prometheus Task。

## 验收结果

- 非法 frame 保存显示错误摘要并聚焦；修正后保存成功。修改 x 后重载恢复原值2和原配置版本。
- PX4/AP 选择配置、保存重载、预检、启动、实时连接/定位/接管和任务反馈、结果读取、Truth 分页均在真实页面完成。
- 同一保存版本的 PX4 两次完成三航点，运行/任务身份不同；AP 普通任务通过，页面实读 armed、GUIDED、有效定位和约3 m高度。
- 取消场景在运行前固定三点各10 s驻留，数值误差门槛不变。第一次确认晚于任务结束，页面拒绝旧确认且未发送cancel。第二次在3.01 m高度提交一次取消，第三点驻留中取消并安全落地，仅前两点记为完成。
- 375×812 实测长版本哈希将页面撑至570 px。最终 CSS 仅新增继承的 `overflow-wrap:anywhere` 和窄屏标题纵排；复测 scrollWidth=360（含滚动条占位），无横向溢出。1440×900 下 scrollWidth=1425，标题、配置及状态可读。控制 JS 未改。
- 键盘激活跳至配置后下一次 Tab 到 name，name 后 Tab 到 stack。错误聚焦及浏览器重载恢复保存配置已验；不据此声称完整读屏器认证。
- 页面正常关闭自有 UE；有查看器时拒绝关闭服务，收尾后正常退出。默认视口已恢复，8765无监听。

## 五次真实运行

原始目录：`validation/operator-ui-20260908/workspace/jobs/`。

| job | 栈 | 正式结果 | 验证内容 |
| --- | --- | --- | --- |
| `160de7e1123e4b438e987b6ce703c710` | PX4 | pass | 首次三航点与UE |
| `bb5eef99eb9a4b3bab5473ea27914f62` | AP | pass | 三航点、实时GUIDED页面反馈 |
| `1262ff4465594257a9dde1d80d42ce80` | PX4 | pass | 同一保存配置重跑、新身份 |
| `b27686cb10084d32bbfe67228587d763` | AP | pass | 取消确认过期；不是取消通过样本 |
| `a4b5e4d570214a5888dd1e5a5ac72fee` | AP | cancelled | 同一10 s配置，空中取消及落地 |

取消 request_id=`f0fa5c1731444d0195d689b7b9a90ad4`；HTTP、`mission-cancel.json` 和任务报告一致。cancel_received 后仅 cancelling→landing_requested→cancelled，无新航点事件；页面将请求受理和实际终态分别呈现。

## 独立审计

`validation/operator-ui-20260908/audit_runs.py` 重新审计五场物理驻留窗口、源码哈希、配置/任务身份、取消文件及HTTP路径。既定0.5 m/0.5 m·s⁻¹/0.15 rad门槛不变。安全落地、children_reaped和无cleanup_errors均成立。

61张原生UE LIVE帧和全部Actor回读通过原有限差。主代理实际查看PX4 25.716 s及AP 53.784 s空中帧，机体、场景和LIVE HUD可辨；UI截图和UE帧分存，未修改像素。

最终 `audit-complete.json` 与 `audit-repeat.json` 字节一致，SHA256：`63a454b01c03aa0bb4ffbef4d9541602d1092e3abfde2bfdef3ecf4c37aee186`。覆盖20条Linux子进程记录（19个不同PGID）及33个Windows PID（含两次控制台服务），当前无对应进程组、运行名进程、socket或Windows PID残留。未用历史55项审计代替本轮，未清理既有用户进程。

服务启动快照与最终代码只有CSS差异，完整摘要已保留。页面在修改后reload，最终布局验收针对新CSS；后台及控制JS未改，五场记录的runtime/control SHA逐项匹配当前源。不宣称CSS在整个调试期间不变。

当前会话工具输出归档：`cua-steps.json`（77步）和 `cua-images.json`（46张原始工具图像，含失败/过渡状态），不是HTTP脚本伪装UI。代表图为[375 px修复后页面](../validation/operator-ui-20260908/cua-2026-09-08T12-26-14.781Z-178db2c863.jpg)和[取消后页面](../validation/operator-ui-20260908/cua-2026-09-08T12-53-11.188Z-0f04fa8f7f.jpg)。

审计器的失败样本保留：首版误要求最终trace总数等于运行中审计总数；实际多出正常地面收尾。修为驻留指标完全一致且最终记录数只可增加。另修正Windows分隔符检查。`audit-attempt1/2`及首次`audit-final.json`失败未覆盖。浏览器保留普通selector失败和viewport reset后的暂时CDP超时；同一页面reload后正常退出，无策略绕过。

## 回归与边界

矩阵 `validation/session-product-checks-zir7OTfY/`：434项，405通过、29跳过；旧预检11通过。新增参数协议4项包含其中；离线模型比较器4项另测通过，未用合成数据冒充数值验收。CSS使用真实浏览器检查，`git diff --check`通过。

#18的前置及本票四项验收已具备证据，2026-09-08 13:07:02 UTC 已发布验收记录并读回 CLOSED/COMPLETED：[GitHub验收记录](https://github.com/unununnnn/wksim/issues/18#issuecomment-5585617347)。#42人工模式操作、#32倍率、#23/G6数值预算及Full其他义务保持开放。参数协议仍未接运行器/真实读写/重启，比较器仍未接获批预算及真实模型采样；Goal不标完成。
