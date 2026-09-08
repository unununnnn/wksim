# #43 保留参数目录的独占租约

2026-09-08。本切片提供本地 POSIX 存储接缝，不证明飞控参数写入、落盘或重启验收完成。

`ParameterStorage(transaction_id, stack, reopen=False, px4_root=None)` 只接受显式 UUID（标准带连字符格式或小写32位hex）和 `arducopter` / `px4`。路径固定为 `/root/wksim-parameter-state-<uuidhex>/storage`；首次创建拒绝任何既有目录，不接管已有非空数据。显式 `reopen=True` 必须匹配原 marker 中的 UUID、栈及可选 PX4 根和目标，且只读校验，不重写参数文件。失败时保留目录供检查，不自动删除或修复。

事务目录和 storage 必须是真实、当前有效UID所有的0700目录；marker 必须是独立0600普通文件。默认存储树拒绝符号链接、硬链接文件和特殊节点。可选 `px4_root` 仅适用于 PX4，必须是绝对真实目录，其 `build/px4_sitl_default/etc` 和 `test_data` 也必须是真实目录。marker 绑定根和两个精确目标，仅允许 storage 顶层由飞控创建的 `etc`、`test_data` 符号链接解析到对应目标；校验不遍历这两个链接，也不主动创建它们。其他符号链接、硬链接文件、非本UID条目和特殊节点仍拒绝。这里不复制固件、不修改固定固件源；根目录参数不是固件准入证明，运行器仍必须完成固定固件的完整 preflight。运行器负责限制飞控进程及配置；该合作式租约不防御同UID恶意进程删除、替换目录或主动关闭继承fd。

运行器使用前调用 `check(stack, px4_root=None)`，校验句柄未关闭、持有fd与当前事务父目录inode一致、marker身份未变、storage路径和内容安全、栈及可选根匹配调用配置，并返回metadata副本。校验只证明调用时状态，不消除校验后同UID进程修改文件的竞争窗口。

租约使用事务目录inode上的非阻塞独占 `flock`，与现有 `Reservation` 一样通过关闭描述符释放，不调用 `LOCK_UN`。`.path` 提供飞控工作目录，`.fd` 应加入 `subprocess.Popen(pass_fds=...)`。父进程关闭句柄或异常退出后，只要继承描述符的进程仍存活并持有fd，第二次获取继续冲突；所有持有者关闭后才可显式重新打开。`.close()` 幂等且不删任何数据；context manager 同样只关闭句柄。

`.metadata` 包含路径、标准格式事务UUID、栈、marker SHA256与是否重新打开，可写入运行结果。没有参数文件快照、复制、迁移或自动恢复；marker SHA256只是身份元数据证据，不是飞控原生持久化证据。AP cwd、PX4 `-w`、子进程清理和结果记录由运行器集成负责。

验证：`python3 -B -m unittest validation.test_wksim_parameter_storage` 在 Ubuntu-22.04 WSL 中运行真实fcntl和短时Python子进程，10项通过。仅测试fixture把模块ROOT替换到 `TemporaryDirectory`；产品不提供可配置存储根目录。保留原7项覆盖首次拒既有/非空、错误栈和UUID marker、UID/权限、符号链接/硬链接、字节保留、两次顺序子进程、父关闭和父异常退出后的继承锁；新增临时固件两个原生链接重开、不遍历固件内容、错误目标/根别名/相对根/缺根/错误栈拒绝，以及关闭句柄、marker篡改和父目录替换检测。没有运行SITL、UE、MATLAB或读取原厂参数文件。
