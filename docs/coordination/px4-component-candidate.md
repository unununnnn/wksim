# PX4组件等待：显式诊断候选

候选 `/root/wksim-px4-component-q0zJqx` 完成1109个构建步骤，manifest为 `component-build.json`，SHA256 `a627423fb28ac4ccf190514ef8f0a4378f41b760311cab523ced3bfb21d0d24b`。它派生自已封存的7RjMjQ land候选，父manifest SHA保持 `45c5332cf06a84952189fcf2eabc5d2e15fde9236c704a5c3d6318e7f5dcb3ac`。

`0005-component-wait-tracing.patch` 只增加三个文件的观察代码。原CAS、位集操作、sem_wait/post、poll超时/continue分支和空组件立即返回原行保留；没有停用logger、移除参与者或跳过屏障。主会话从实际基线生成diff，`git apply --check`通过。早期代理草稿违反空组件分支并会逐周期输出，已拒绝，未用于构建。

仅 `WKSIM_PX4_COMPONENT_TIMING=1` 启用，默认与其它值无额外时钟读取/输出。Linux `syscall(SYS_clock_gettime,CLOCK_MONOTONIC)`绕过PX4模拟时钟宏；注册打印bitmask/TID/task，send分别计poll/prepare/component/send，组件等待记录入口used/progress/missing以及最近释放观察。正常poll包含0.5×节奏等待，因此仅poll>20ms或其后活跃段>2ms输出；组件wait>2ms输出，避免逐周期刷日志。这些是诊断采样阈值，原倍率/物理门槛不变。

release时间与component是分别读取的观察值，不能保证原子配对；注册/注销及原有竞态下尤其不能单凭它们断言根因。系统取时失败的零值也不能作为有效计时证据。原生计时自身及stderr写入可能产生开销，后续分析须单独说明。

构建/源码/依赖封存通过；只允许与父源树相比恰好三个文件变化且字节等于应用补丁的结果。完整bin/etc产物、构建日志、依赖输出、补丁/构建器/校验器和祖先身份均入manifest。显式ArUco配置只接受匹配的component根目录/manifest文件名；正常land路径仍走原校验器。启动时只向PX4子进程注入已校验的环境，并留存实际原生源文件。

18项路径/配置/校验器/循环检查在Windows和WSL通过。原生屏障检查编译了候选实际component.cpp/header，使用POSIX semaphore平台shim：空组件不阻塞、未收齐组件不放行、收齐后完成；off/非法值的额外clock_reads=0且stderr为空，on正确记录释放者。这个检查不是完整PX4飞行或完整平台集成测试。

独立准入 `admission-exec.json` 为ok=true且native_component_timing=true。两次手工复查失败记录也保留：缺少正确overlay，以及WSL额外shell对PYTHONPATH的提前展开；用`wsl --exec`保留已加载环境后通过，未改资源来绕过检查。运行器本就使用显式exec入口。

证据 `validation/px4-component-candidate-01` 与 `validation/px4-component-barrier-01`；原生二进制留在私有依赖目录。当前仅诊断候选，尚无该固件的真实飞行验收，不作生产提升。
