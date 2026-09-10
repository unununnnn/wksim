# ArduCopter 相机跟踪完整采集

第13场 `aruco-track-56b317f796` / `3662bc056ae74e0abed662214a8010bd` 完成双机起飞、ArduCopter 相机跟踪、遮挡、恢复、降落和退场。运行器与管理器退出0，状态为 `captured_pending_independent_audit`。历史失败保持原判；本场尚不等于 #104/#40 或 Full 完成。

独立物理/几何审计通过：90帧真实RGB；跟踪区间57820..69820的12,001个物理tick全部检查，最大跟踪误差0.475563860m，恢复末窗最大误差0.035399126m，均低于冻结的0.65/0.3m。两机位置范围、高度、倾角和最终落地检查通过。

原始倍率计划单锚、无追赶核验通过，最坏累计迟到86.533429ms；15个完整10s窗通过，首60s相对误差约0.0811%。没有完整60s双机空中窗口，因此这不是完整三epoch G2验收。

本场显式启用了12adf90的后台模型日志选项。两份模型日志分别118,955,260和124,909,836字节，submitted/written与实际文件大小相同，writer均关闭、无错误、无存活线程。五份监督器后台日志也全部完整退场。默认同步模式未改变；单场通过不能证明间歇倍率问题全部解决。

实际命令：

```powershell
& work/dependencies/aruco-python/Scripts/python.exe -B tools/run_aruco_tracking.py --manifest validation/ue55-build-f0409a874ed243cdbad4ac9cb38d886d/candidate-manifest.json --candidate validation/aruco-tracking-candidate-01/candidate-arducopter.json --output validation/40-aruco-tracking-13-ap --async-evidence --async-model-evidence --write-timing
& work/dependencies/aruco-python/Scripts/python.exe -B tools/audit_aruco_tracking_physical.py validation/40-aruco-tracking-13-ap --output validation/coordination/aruco-13-ap-physical-audit.json
python -B tools/audit_aruco_rate.py validation/40-aruco-tracking-13-ap --output validation/coordination/aruco-13-ap-rate-audit.json
```

源码、配置、依赖、原始CDR、图片、模型轨迹及退出记录在 `validation/40-aruco-tracking-13-ap`。归档包含572个文件，7个有序分片，完整压缩包SHA256为 `55e1345b8929ae10e3e15c9fe152f51a4f5f8c46ed8c342a6990415c3adc8754`，逐成员校验通过。正式验收仍须结合本场公共命令链、失效/HOLD/恢复和原生设定值/发布者证据。
