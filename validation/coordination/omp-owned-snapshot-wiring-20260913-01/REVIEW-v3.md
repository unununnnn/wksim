# omp-owned-snapshot-wiring-review-20260913-01 v3 复核：CLEAR

历史：v1 CLEAR 已撤回（见 REVIEW.md 撤回条）；v2 审查因 v3 交付而中止。本结论仅对 v3 候选 SHA **`1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373`** 有效；作者再改须重钉。

方式：从候选字节按标记提取真实块（begin/end 1–10）exec 于 fake 命名空间（`verify_v3_blocks.py`，7/7 OK）；不复跑 v1/v2 或作者 16 项测试；D 的成功路径次序与失败文件 validated=false 结论不在本轮范围。

## 前次遗漏项逐项（全部通过，无阻断）

1. **早 pin/import/来源校验**：块2 在 check_isolation/任何子进程之前：先 `digest` 钉 SHA（错 SHA→`differs from the reviewed pin`，无需 import 即拒），再 import，再 `__file__` resolve 比对来源（`unexpected origin`），最后签名接口检查。缺模块→ImportError 在门处抛出；结构上证：块2 位于首个 `subprocess.Popen` 之前。
2. **取消传播**：before 捕获为 `except Exception`；KeyboardInterrupt 实 Exec 穿透块5抛出，普通 RuntimeError 落 `before_error` 且不置 `before`。
3. **boot 变化零 PID 读**：before 钉 `boot-B`；after 时当前 boot 变 `boot-A`→`after_error='boot changed'`，capture 调用计数不变（零 PID 读）；capture 回报 host boot 与钉不符→`host boot differs` 硬错误且不置 `before_validated`。
4. **普通 metadata 异常不掩盖业务错误**：块7 digest 抛 OSError→`metadata_error` 落账；在飞业务 RuntimeError 原对象穿透（assertIs），status 保持 failed；validated=false 的文件只作 raw 保留（块7 明文 note）。
5. **默认关零副作用**：flag 缺省下 exec 块2/5/7 后 `capture_owned_scheduling` 不在 sys.modules，result 无 `owned_scheduling` 键。
6. 附带实测：after once 幂等（两次调用一次 capture，`after_attempted` 守門）。

## 结论

**CLEAR（限上述范围，限 SHA `1c600d7f…`）**。组合拒绝清单含 spin/pause/scene/recovery/early-work/planner/model-promotion + dds_loss。正式防护不变：pass→observed + 父探针标记键。

## SHA-256

- 候选：`1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373`
- 本验证器：见交付消息实测
