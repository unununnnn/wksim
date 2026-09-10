# GNSS flight contract v1 — implementation decision

2026-09-10. The primary agent owns gnss_task.py, gnss-flight-v1.json,
gnss_physics.py, gnss_candidate.py, run_gnss_flight.py/run-gnss-flight.sh and
audit_gnss_flight.py plus their tests/evidence. This extends the completed native
scheduled AP prerequisite. No original #109 fixed-window evidence is changed.

The experiment uses the previously measured healthy 3m native position profile,
ENU [2,3,3], yaw0, continuous6s within .3m/.3m/s/.15rad. The physics owner chooses
an aligned start at least2000 native ticks later. One15s stop-new-GPS interval
exceeds AP's source-observed4s driver timeout and7/10s position-aiding retry times;
PX4 declares GNSS intermittent after1s. These timing facts motivate observation,
not a promise of a particular airborne safety result.

No native failsafe parameter is overridden. Task withdraws on native navigation
loss; source GNSS, native fix validity, estimator validity and transport connection
are separately recorded. The unchanged model continues IMU/physical truth. During
outage retain the existing15deg/4m/4.5m experiment envelope, with ground permitted
at height>=-.3m because native landing remains possible. A violation is a failed
run; do not loosen the envelope after a result.

Recovery waits up to45s after the interval for fresh native GPS/navigation data,
observes1s without automatic task reacquisition, then sends a new explicit native
hold request. Native-confirmed ground requires disarmed ground and a new explicit
arm/takeoff; airborne recovery captures the current valid pose. A new command_id
and request_id move to a distinct ENU [3,2,3], held2s within the same healthy bounds,
then an explicit LAND and actual disarmed ground/cleanup finish the run. This is
not a replay of the old waypoint. It neither extends #22 Agent-only acceptance
nor claims G6, HIL or joint-rate completion.

The runtime reports observed, not pass. Independent raw CDR/serial/MAVLink,
continuous1ms physical, source-age, no-output-after-withdrawal, new-request and
terminal audits determine acceptance. Failure and native-policy behavior must
remain visible. The exact configuration SHA is in gnss_task.py and each run.

## v2 policy correction after the preserved v1 failure

The first real PX4 run invalidated navigation and withdrew Control correctly,
then the actual parameter combination COM_OBL_RC_ACT=0 / NAV_RCL_ACT=2 caused
Position -> Return -> degraded-position fallback. The model moved toward home
and crossed the4m radius around the original waypoint. This v1 run remains failed.

The new separate gnss-flight-v2.json explicitly selects PX4's documented native
COM_OBL_RC_ACT=4 (Land) on loss of the offboard stream. It retains the same15s
sensor outage, original waypoint,4m/15deg/4.5m envelope and recovery criteria.
This changes the declared failsafe policy, not the numerical budget or old result.
The original v1 configuration is retained. The new audit must verify actual ULog
parameter readback and native mode feedback; a configured value alone is not proof.
AP native EKF failsafe remains unchanged. This is an explicit simulation experiment
configuration, not a production default or a hardware safety certification.

## v3 AP explicit loss landing

The first AP flight proved actual GPS invalidity and task withdrawal, but waiting
only for the native EKF action allowed drift past4m before descent finished. The
run remains failed. v3 retains all v2 physical limits and the same15s GNSS outage,
but requires an explicit public LAND request immediately after observed AP task
withdrawal, with native acknowledgement. Recovery still waits for fresh native
navigation and new explicit task requests.

Control may observe an explicitly requested LAND or LOITER acknowledgement while
withdrawn and in INIT, including native failsafe. This exception cannot enable a
position stream, arm the aircraft, or enter COMMAND_CONTROL. Existing admission
and new-task checks still apply;51 control regression tests pass. No old failed
run is reclassified, and no hardware policy is implied.

## Recovery datum and reference shaping

The AP recovery run exposed a real home update on re-arming: WksimState pose is
home-relative (AP_DDS_Client.cpp uses get_relative_position_NED_home). The task
now binds the initial and current native home latitude/longitude/altitude and
translates the same physical goal into the current local frame. Physics truth
is not used as a control input. The independent audit checks the conversion and
still checks arrival at the original physical-world target.

A subsequent direct position step exceeded the retained15deg transient tilt
limit. Recovery now advances the reference at the already-declared .3m/s speed,
with increasing new command/request IDs, and then holds the unchanged final
point. No waypoint, outage duration, physical envelope or recovery tolerance was
relaxed. All unsuccessful runs and their original parameter contracts remain.
