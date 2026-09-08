# Humble 原生订阅匹配检查

AP参数维护首轮的第二阶段在 `native_motion_unique_publishers` 超时。没有liveliness回调，因此旧信封未发布，第二次参数操作和飞行未开始；保留失败及待恢复状态。不能用图中的发布者数量直接宣称订阅已匹配。

本机 `/opt/ros/humble/include/rcl/rcl/subscription.h` 明确提供 `rcl_subscription_get_publisher_count(const rcl_subscription_t *, size_t *)`，返回实际matched publisher数量。`tools/ros_subscription_match.py` 用标准库ctypes绑定已安装librcl.so，固定参数/返回类型，在 `with subscription.handle` 期间取其pointer，并用公共topic-name API核对同一主题，非零错误码立即失败。Humble handle的上下文管理器返回None，首个隔离测试因此报错；已改为访问原handle，失败日志保留。

`validation/test_ros_subscription_match.py` 在私有net/ipc/mount与tmpfs shm、Humble/FastDDS、domain77中实际通过：无发布者0；BEST_EFFORT发布者面对RELIABLE订阅时图1/匹配0；兼容发布者图1/匹配1且收到真实String；销毁后图0/匹配0。测试仅用 `/wksim_match_test`，不启动飞控、不接触原生运动或参数通道。成功原始日志 `validation/parameter-maintenance-20260909/matched-count-test-02.log` 保存库、头文件与工具SHA256。初始失败为同目录 `matched-count-test.log`。

可复跑方式：在 `unshare --net --ipc --mount --propagation private` 内启动loopback、挂载私有/dev/shm，source Humble，设置 `WKSIM_TEST_PRIVATE_ROS=1 ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp`，执行 `python3 -B -m unittest validation.test_ros_subscription_match -v`。测试另断言自身net namespace不同于PID1。正式 `tools/check-session-product.sh` 的既有私有环境也启用该测试；普通未隔离单测不发ROS流量。

维护观察窗口保留唯一Control图GID、实际匹配数、完整拒绝事件、旧信封CDR和至少1秒零原生样本检查。当前回调仍不提供逐包MessageInfo，图GID不会被描述成逐包来源。这是匹配/传输接口验证，不独立证明旧命令隔离或飞控重启已验收。
