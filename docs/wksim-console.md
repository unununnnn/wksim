# wksim 本地实验工作台（#18 已验收）

2026-09-08：真实内置浏览器操作、双栈任务、保存重跑、空中取消、结果分页与键盘/窄屏检查通过，#18已关闭。浏览器旧限制已解除，375px哈希溢出已修复；原始失败、五次运行与收尾证据见[UI收口报告](2026-09-08-console-ui-closure-report.md)。本文后续带2026-09-05/06时间的限制是历史状态，其他Full边界仍有效。

Windows 本地 Python 标准库服务及离线 HTML/CSS/JavaScript；不需要 npm、CDN、Electron 或新增 ROS 依赖。服务调用已有 `tools/run-wksim.sh`，飞行命令仍由 Prometheus 正式 Task 发送。浏览器、UE 和证据查看不负责物理节拍。

## 启动

在本仓库根目录的 PowerShell 中执行：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 -B -m Simulator.wksim_console.server --port 8765 --data-root work/operator-console
```

页面地址为 `http://127.0.0.1:8765/`。仅接受该精确本机地址，不绑定局域网，不提供任意文件浏览器。已有本机环境为 Ubuntu-22.04、ROS2 Humble 和已核验的双飞控候选；高级配置可选候选，但必须经过真实预检。服务不会安装、编译或替换飞控环境。默认新数据目录；不接管非空的非控制台目录。

## 操作流程

1. 选择 PX4 或 ArduCopter，编辑 ENU/body_flu 航点和任务配置。原始 JSON 与表单互通；配置名称限 ASCII 字母、数字、短横线和下划线。
2. 保存、重载配置，运行候选预检。编辑配置后旧预检失效；候选准入不等于定位、接管或飞行就绪。
3. 启动实验。每次产生新的执行 run_id 和显示 socket，保留原始配置及其哈希。可选 UE 先准备；此时物理尚未创建。UE 就绪、失败或主动关闭后，再启动正式仿真。显示失败会明确报告，实验仍可无界面运行。
4. 观察连接/定位、源数据新鲜度、控制模式、任务状态及航点进度。原始状态和事件可展开。WSL 接收时间与 Windows 观察时间分列，不伪造跨宿主映射；过期数据不表示当前就绪。
5. 实时许可允许时，可明确暂停/恢复任务。确认框冻结实验、任务、代次与令牌，确认前再次核对；任何变化须重新确认，不自动替换令牌。暂停停止派点，物理与飞控继续；恢复重新接管，沿原记录 ENU 目标重新完整停留。提交成功不等于任务确认，需观察匹配 request_id 的反馈。
6. 取消须确认当前 mission_id。受理不等于落地；若任务仍拥有控制权，则停止后续航点并降落。暂停中取消不会自动抢回控制：需显式恢复后 LAND，不再执行航点，或由其他控制者完成落地。不能用关闭页面/关闭 UE 代替取消。
7. 终态读取结果和四种记录流。结果接口以严格 JSON 包装原文、SHA-256 和数值标记；原始报告的 NaN 表示未提供的遥测，不替换成零，不改写原文件。记录分页是离线回看，不会重演仿真。
8. 关闭 UE 后，可在无活动任务/预检/准备阶段时关闭本地服务。正常关闭只处理自己创建的显示进程；服务重启后不自动接管历史进程，也不把旧 UE 状态标为实时。

配置覆盖使用版本比较，多个服务不能同时拥有同一个数据目录。本控制台串行启动独立实验；已有 CLI 并行隔离能力仍保留。同场景联合权威时间仍由其他票据负责。

## 验证及当前限制

Windows 检查：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 -B -m unittest validation.test_wksim_console_records validation.test_wksim_console_visual validation.test_wksim_console_workspace validation.test_wksim_console_http -v
```

真实服务验证（服务已启动；每次选择新的输出目录）：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --stack px4 --view --evidence validation/my-px4-console-check
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --stack arducopter --case cancel --evidence validation/my-ap-cancel-check
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --stack px4 --case pause-resume --dwell-s 10 --evidence validation/my-px4-pause-check
& 'D:/date/miniconda/python.exe' -X utf8 -B tools/validate_operator_http.py --stack arducopter --case pause-cancel --dwell-s 10 --evidence validation/my-ap-paused-cancel-check
```

这些命令是真实服务/仿真测试，**不是浏览器交互验收**。暂停流程的10秒停留是运行前固定的观察配置，不改变误差预算。测试客户端失败不会杀死飞行启动器；若失败时任务已暂停，仍需观察当前身份并显式操作，不能假定会自动恢复或自动降落。内置浏览器因无法核验管理员策略拒绝访问；未绕过策略，尚无实际表单操作、响应式布局、键盘流程或页面截图验收。

暂停/恢复的操作记录保留在当前页面内存；刷新后不恢复未取得的提交回执。响应丢失显示“未知”，不自动重试，不把同令牌的其他回执冒认为当前请求。完整原始请求和服务审计仍在实验目录中；具体身份契约见 [console-contract.md](console-contract.md)。

后续已修复太阳可移动性和显示就绪边界，接入并保留 Prometheus 原 P450 机体/旋翼资产；采用本机8 GB GPU的轻量显示配置。原生画面和双栈飞行通过记录见 [P450 显示报告](2026-09-06_p450-view-report.md)。物理仍明确标记为 quad-X，未完成 P450 动力学校准。UE 冷启动时延有波动：短任务可能在重开查看器就绪前结束，失败与固定10秒航点停留复跑结果均保留；不能据单次回读或重试声称全部显示条件稳定。

异常杀死服务后，未证明 UE 包装器后代/WSL 中间进程自动全树回收；历史记录不会变成新的控制权限。实际正常流程的残留检查单独保存在本轮审计。此服务也不宣称抵御具有同一主机账户写权限的攻击者。

原始工作台证据见[第四批报告](2026-09-06_operator-workspace-report.md)，后续见[P450 显示报告](2026-09-06_p450-view-report.md)和[UI收口报告](2026-09-08-console-ui-closure-report.md)，接口见[console-contract.md](console-contract.md)。#18已关闭；Full Goal、数值预算和其他未完成门槛不因此完成或缩减。
