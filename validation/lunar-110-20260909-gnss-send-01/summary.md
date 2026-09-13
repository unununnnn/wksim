# #110 / 45-px4-injection

Implemented the optional real HIL_GPS send boundary in px4_mavlink.py. The gate is wired into both normal and duplicate-actuator send_sensors paths. Only GNSS is gated; IMU/resend and model stepping remain unchanged. No physical budgets changed.

Allowed implementation files: Simulator/wksim_core/px4_mavlink.py, Simulator/wksim_core/gnss_event.py, validation/test_gnss_px4_injection.py. Additional evidence is confined to this new directory under the handoff guide's shared evidence allowance. AGENTS.md and the handoff guide are excluded from staging.

## API and evidence schema

Construct GnssEventController(run_id, epoch, vehicle_id, max_age_ticks=..., plan=GnssEventPlan(...)), then GnssSendGate(controller, record_callback). Call serve(..., run_id=..., vehicle_id=..., gnss_epoch=..., gnss_gate=gate). Identity mismatch is rejected before socket/model resources open. No CLI default or default profile is changed. The future runner (#121) must freeze its actual plan/budget/resource identities and provide a durable synchronous recorder (for example JSONL in an exclusively created run directory).

Records use schema wksim-px4-gnss-send-v1. Every candidate result retains identity, authority tick, the original 13-field GPS tuple, full decision/plan/budget, attempted, success, error and raw_frames_hex. A separate phase=attempt record precedes the send call; phase=result records suppression, validation failure or send outcome. Captured bytes are the actual MAVLink frame handed to sendall, not a re-encoded reconstruction. success means the local send call returned; it does not prove peer receipt or FC acceptance. Exceptions propagate; partial TCP delivery is unknown and old samples are not retried. Recorder failure propagates; external process termination/storage failure still requires the runner to identify incomplete records.

GPS source time is preserved from gps_arguments(state). source_tick is ceil(original time_usec / 1000), never arrival tick; both acquisition-grid age and original microsecond age are checked. sequence uses authority tick, so repeated actuator callbacks cannot advance GPS freshness. Foreign run/epoch/vehicle, future, stale, duplicate and old sources are rejected. A reset requires a fresh epoch and clears the old event plan; runtime restart must explicitly bind the new epoch. This is the current model epoch-relative timestamp contract, not support for arbitrary Unix/GPS clocks or proof against a dishonest producer.

## Verification

Windows: 28 tests passed, zero skipped (12 new send-boundary tests, 10 GNSS controller tests, 6 existing protocol tests). WSL Ubuntu-22.04: 34 tests passed, zero skipped, including six native-model regressions. Raw logs and JSON send records are windows-tests.log and wsl-tests.log; source/test/log hashes are in identity.log. No runtime configuration was changed; the test's plan and budget are frozen in its hashed source. Windows Python is 3.13.11; its pymavlink common.py SHA256 is 3ea65f5611b53b4e9cab51fb79d57746f0be4022497686c623ddcf66681ef15e.

Exact commands from the wksim root (WKSIM_GNSS_EVIDENCE=1 enables JSON records in test output):

```powershell
$env:WKSIM_GNSS_EVIDENCE = '1'
python -m unittest validation.test_gnss_px4_injection validation.test_gnss_event validation.test_wksim_core.ProtocolTests -v
wsl -d Ubuntu-22.04 -u root -- env WKSIM_GNSS_EVIDENCE=1 /usr/bin/python3 -m unittest validation.test_gnss_px4_injection validation.test_gnss_event validation.test_wksim_core -v
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --cached --check -- Simulator/wksim_core/px4_mavlink.py Simulator/wksim_core/gnss_event.py validation/test_gnss_px4_injection.py validation/lunar-110-20260909-gnss-send-01
```

Tests use the real pymavlink encoder, Sender.sendall and local socket pair receiver with synthetic state inputs. Receiver bytes are compared with recorded bytes, and decoded GPS fields are checked unchanged. Coverage includes exact [200,400) boundaries, cadence, duplicate GPS with IMU resend, no-hook regression, no-plan invalid-fix preservation, original source timestamps, inclusive freshness budget, stale/future/foreign rejection, outage-source replay at recovery, new epoch, socket error, invalid input and recorder failure.

Read-only model source inspection: archive SHA256 d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed matches model.py. Generated source assigns HILGPS30d[0] from rtb_time_usec at line 7727; model.cpp copies HILGPS30d unchanged into state[90:120]. Initial UTF-8 decoding of the archive member failed; GB18030 decoding succeeded. No vendor material was modified or committed.

WSL Python is 3.10.12; /root/.local/lib/python3.10/site-packages/pymavlink/dialects/v20/common.py SHA256 is a7c6b23d908322134d19cb94b937c1ea6b1f5d5ffa9d1b0ad139174bf8d75809. Logs preserve shell output (including WSL's localhost-proxy diagnostic). Default git whitespace checking reported CRLF as trailing whitespace; the repository-prescribed cr-at-eol check is used without rewriting raw logs.

## Acceptance and limits

Both #110 acceptance items are satisfied by the bounded source seam, native encoded socket tests, provenance, commands and raw logs. Close only #110. No GNSS interruption flight, EKF recovery, task revocation or explicit flight takeover was performed or claimed; those remain #121/#111 and parent #45 work. WSL native-model tests build a fresh temporary library using the existing test helper; no FC/ROS/UE process is started. Test sockets close via unittest cleanup; no test process remains running. Existing R1/RateUnmet conclusions are unchanged.

Actual model/reasoning setting cannot be independently verified through this session's available interface. User dispatch specifies gpt-6-astra/low; this report does not assert unverified runtime metadata. No subagents were used.
