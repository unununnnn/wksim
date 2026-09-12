# Fresh Control installation check

Built on 2026-09-12 in WSL Ubuntu-22.04 using `bash tools/build-joint-control.sh` after clearing ROS/CMake/Python environment variables. Candidate: `/root/wksim-joint-control-ZlTVa4`.

The source baseline was `b1ad906` plus the runtime/message-asset closure changes recorded by `build.json`. Manifest SHA256: `3d04d53a5c41d374ee623d16a265e8816d481e5d4433f23a60140a8e8184ecc4`. The live sealer subsequently compared the repository, staged files and installed files successfully: 15 Simulator Python files and two frozen message assets. The manifest also retains the original Control package, native transport and message-overlay identity checks. No compiled binary is included here.

`installed-smoke.py` was copied into the candidate's `smoke-outside` directory and run there with only installed overlays sourced. The process used private network, IPC and mount namespaces, fresh `/dev/shm`, loopback networking and ROS_DOMAIN_ID=79. The decoder and real ROS2 node were constructed with production `use_sim_time=true`; all 15 imported Simulator modules and both message pins resolved within the installed prefix. The node socket and ROS context were closed. `installed-smoke.json` is the original output; stderr is retained separately.

This proves installation/import/resource availability and construction, not planner causality, message delivery, FC control, PV or Full acceptance. No session or trajectory was supplied and no command was sent. The WSL launcher printed a systemd user-session warning; the build and isolated smoke both exited zero.
