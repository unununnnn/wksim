set -euo pipefail
cd /root/wksim-release-acceptance-fe3
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset CMAKE_PREFIX_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH ROS_DISTRO PKG_CONFIG_PATH WKSIM_JOINT_CPU_TIMING WKSIM_JOINT_RATE_TIMING_PROBE
export PYTHONDONTWRITEBYTECODE=1 WKSIM_JOINT_RATE_TIMING_PROBE=1 WKSIM_JOINT_CPU_TIMING=1
python3 -B - <<'PY'
import hashlib,json,pathlib,time
root=pathlib.Path.cwd();p=root/'validation/spin-cpu-mixed-20260913-01'
r=json.loads((p/'pre-run-identity.json').read_text())
for name,digest in r['source_sha256'].items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('source changed '+name)
for name,digest in r['manifest_sha256'].items():
 if hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()!=digest:raise RuntimeError('manifest changed '+name)
with (p/'launch.json').open('x') as f:json.dump({'started_unix':time.time(),'diagnostic_only':True,'full_acceptance':False},f)
PY
set +e
bash tools/run-joint-flight.sh \
 --task-profile xy_velocity_z_position_yaw_v1 --async-model-evidence --manager-gc-freeze --rate-spin-cpu-timing \
 --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
 --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
 --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
 --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
 --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
 --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219 \
 2>&1 | tee validation/spin-cpu-mixed-20260913-01/run.stdout.log
formal_exit=${PIPESTATUS[0]}
printf '%s\n' "$formal_exit" > validation/spin-cpu-mixed-20260913-01/exit-code.txt
exit "$formal_exit"
