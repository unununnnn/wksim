# 原生诊断v2：避免注册热路径输出

`/root/wksim-px4-component-ZNq7Mp`已构建并封存，manifest SHA256 `9806c6cbbf5318a33a9359de2846540a4a807a79101a2a426d78ec8d7e792b80`，仍从不变的7RjMjQ land候选派生。v1根目录q0zJqx保留，不就地修改。

五个受限源文件包含原三文件和WorkQueue.cpp/h。v2去掉register_component的全部诊断输出，因为它会从WorkQueue::Add持锁路径高频调用；原注册、队列操作、进度、注销、sem_wait/post均保留。新增释放类别只作独立原子观察：1=progress，2=unregister，仍不保证多个观察字段原子配对。

队列第一次从空闲变为活跃时，在现有锁内保存真实单调时间；工作线程记录唤醒和取得队列锁的时间。工作项名称在Run前复制（最多95字符），Run后不再读该对象，因为它可以自删除。慢工作项记录发生在重新取得队列锁之前；慢批次记录发生在注销及解锁之后。只记录超过2ms的工作/批次，不输出常规注册流。原send/poll观察门保持不变。

真实源树的git apply检查、完整1109步native构建与五文件严格delta封存通过；资源准入 `ok: true`，manifest SHA256为 `9806c6cbbf5318a33a9359de2846540a4a807a79101a2a426d78ec8d7e792b80`。候选屏障源+POSIX shim的off/on/非法开关测试通过，空组件不阻塞、必须收齐组件；off和非法值没有额外clock/log。解析器增加工作/队列区间，允许旧唤醒令牌先于新入队，但取得队列锁不能早于该批次ready。

`validation/px4-component-workqueue-04` 从候选的真实 helper、Add、SignalWorkerThread、Run 方法体逐段提取并与标记shim编译。同一WorkQueue实例用条件变量在第一次unregister后启动第二批；静态顺序检查还要求unregister→组件复位→解锁→QUEUE日志。两批各自重新注册、更新ready、执行超过2ms并自删除的WorkItem、注销并输出一条QUEUE。off/非法开关均为2次注销但零trace；on为2条WORK/2条QUEUE，组件从1变2且第二个ready严格更新，ASan无UAF/泄漏，线程无死锁。Windows相关16项检查通过（1项WSL源测试跳过），WSL实际源7项全部通过；解析器对本次trace得到work=2、queue=2。

这里不是飞行或倍率通过声明；后续仍需run20同场真实验证，任何失败继续保留。
