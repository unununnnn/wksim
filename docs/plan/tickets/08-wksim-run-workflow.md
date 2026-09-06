# 08 · wksim界面配置到任务结果的完整流程

状态：2026-09-06 JST 已实现主干并完成服务层真实双栈联测；**仍 open**。前置 #11/#15/#16/#17 均 closed；实际浏览器交互未验收、UE 冷启动时延稳定性待改进，不能关闭本票。

工作台暂停/恢复跟进：新增冻结身份确认、过期拒绝、明确提交/受理/完成反馈；实际HTTP→正式Task双栈恢复与暂停后取消4例通过，16个Linux组/12个Windows启动器无残留。跨平台回归、真实物理与源码审计见[报告](../../2026-09-06_console-mission-actions-report.md)。原生HTML/Node逻辑已检查，但没有实际浏览器点击、键盘/读屏器或布局验收，不勾完本票。

本轮记录：[第四批报告](../../2026-09-06_operator-workspace-report.md)。51 项 Windows 检查、185 项 WSL 回归、6 个真实 HTTP/飞控服务用例及全部尝试残留审计通过；没有用它们替代下列用户界面验收。内置浏览器管理员策略校验不可用，未绕过。原始 UE 帧存在冷编译黑帧/照明偏暗，仍需修正和图像复核。

后续 [P450 显示报告](../../2026-09-06_p450-view-report.md)：已保留原项目 P450 真实资产并修复黑/暗帧，88项 Windows 检查和185项 WSL 回归通过。5次飞行本体均 pass；最后双栈固定10秒停留用例有空中关闭/重开、真实 Actor 和原生 LIVE PNG，全部尝试的20个 Linux 进程组及53个 Windows 启动进程残留审计通过。AP 同配置第一次显示启动超出任务窗口、复跑通过的差异保留，不将其写为稳定性已解决；上述旧报告描述仅为历史状态。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

在wksim界面选择实验、启动、执行任务、观察状态、停止并定位结果，能再次运行同一配置。

## Acceptance criteria

- [ ] 界面调用同一正式操作入口，不自行维护飞控控制逻辑；无界面入口仍可用。
- [ ] 用户可见配置校验、连接/定位/接管状态、任务进度、错误及结果位置。
- [ ] 保存并重载同一配置后行为一致；失败后修正配置可再次运行。
- [ ] 完成一次真实双栈分别运行的交互验收，保留UI观察与机器可检验的证据关联；不复制厂商品牌。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [实验能力预检与候选身份核验](https://github.com/unununnnn/wksim/issues/11)
- [单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)
- [已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16)
- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)

## Parallel boundary

本票建议归属：产品界面。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
