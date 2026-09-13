# Live ROS1 sender transport: passed

The real sender process subscribed to ROS1 Bool, traj_utils/Bspline and private Empty hold/cancel topics in an isolated Rfly network/IPC/mount namespace. A separate fixture publisher supplied the previously captured real EGO message. The actual TCP receiver observed gate-open, Bspline, hold and cancel in one stream with sequence numbers 1–4. It compared all control points, knots, trajectory ID and the original start time 2601000000ns. `tcp-stream.bin` is the received stream; `result.json` includes decoded frames and original envelopes.

After cancel, the fixture published another Bspline and gate-open. No additional bytes were observed during a bounded 0.3s wall-time window, and the sender remained connected. The sender and ROS master subsequently exited zero. Project source hashes were unchanged throughout.

Attempt 01 is retained separately. It received gate and Bspline but failed a fixture assertion comparing coordinate tuples with lists; it did not demonstrate altered coordinates. The corrected comparison checks the existing tuple-shaped decoder API. The final fixture retains received TCP bytes on both success and failure.

Inputs were explicitly paced by observing each frame at the sink, so this does not assert original publication ordering across arbitrary ROS topics. There was no ROS2 transport node, ControlNode, native FC, control ACK or physical flight in this run. A delivered cancel remains a request, not proof of FC stop. Run the script under the Noetic/full-EGO overlay and private network/IPC/mount namespaces with `python3 -B validation/run_ros1_sender_probe.py ABSOLUTE_OUTPUT`.
