# AP 第15场：完整闭环采集及原生末尾 HOLD

`aruco-track-aa766cf3f8` / `d342bbd7a8c449e19aa63c9dc268c50e` 正常完成并退场，驱动及管理器退出0，无authority fault或清理错误，90帧。与第14场相比，仅增加既有 `--cpu-timing`，源码、固定资源、物理和倍率门槛不变。

已通过的同场审计：

- 12,001个物理tick（57720..69720）：AP最大跟踪误差0.472222570m，恢复末窗最大误差0.148149505m；几何、范围、高度、倾角、两机落地通过。
- 倍率单锚、无追赶/重锚；最坏累计迟到97.970542ms，15个完整10s窗与首60s窗通过。没有完整60s双机空中窗口，不代表完整三epoch G2。
- 公共原始链及loss-HOLD：90帧/89次消费、72 MOVE/16 HOLD，14个恢复周期闭合。原始审计器仍以pending返回，原生内容由下列独立审计补证，未改写其范围。
- 72条MOVE的真实原生字段精确匹配。15段post-MOVE HOLD共173个原生位置样本匹配；末尾HOLD request91首次得到真实原生位置样本（1个），之后才LAND，补齐第13场未执行末尾HOLD的缺口。
- AP229次/PX4161次发现图快照、完整类型集合、Control节点与完整writer GID、raw样本匹配全部通过；仅证明记录时刻的图状态。五个监督器及两模型后台writer全部完整退场。

计时探针观察到，本场最大峰值转移到tick57500附近，解锁窗口47000..47500没有重现第14场的20ms组峰值。57480..57540窗口中已采样native_inputs累计墙钟53.861ms、线程CPU7.202ms；单个AP输入等待最高9.584750ms，其中监督器线程CPU1.081238ms。说明该窗口主要耗在等待/失调度，而非监督器自身CPU计算；尚不能据此确定AP飞控、网络、WSL或Windows的具体根因。GC最高0.300441ms，不能独自解释该峰值。没有放宽旧失败判定。

证据目录 `validation/40-aruco-tracking-15-ap-cpu`，577个归档成员、7分片，SHA256 `2bba6fedae46cbdbf48b9934605d42d1557096f7b31ea92f0b1903ca03c94771`。独立输出为 `validation/coordination/aruco-15-ap-{physical,rate,raw,native-moves,native-holds,publishers,rate-replay,arm-timing,peak-timing}.json`。

下一步用相同修复完成PX4对应运行，并补两栈原生载荷内时间戳的独立核对。连续setpoint没有原生ACK通道；公共受理、原生下发和动作完成分别报告。#104/#40及Full尚未关闭。
