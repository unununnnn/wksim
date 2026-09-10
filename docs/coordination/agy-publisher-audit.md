# Coordination: ArUco Native Target Publisher GID Binding & Exclusivity Audit

## 1. Scope & Core Architectural Boundary

This document records the offline investigation into whether the native target publisher GID (captured in `aruco-raw-dds.jsonl`) can be bound to the actual `Control` node process/endpoint, and whether full-graph publisher exclusivity (全图发布者独占性) can be claimed from the preserved evidence of two successful joint flight runs:
- **Run 10**: PX4 tracking candidate ([`validation/40-aruco-tracking-10`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/40-aruco-tracking-10))
- **Run 13-ap**: ArduCopter tracking candidate ([`validation/40-aruco-tracking-13-ap`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/40-aruco-tracking-13-ap))

### Non-Negotiable Investigation Rules:
1. **Passive Observation $\ne$ Full-Graph Exclusivity**:
   - In DDS / ROS2, passive capture via `rmw_take` (`aruco-raw-dds.jsonl`) records only packets that are actively published into the network.
   - If a duplicate, rogue, or dormant publisher exists on the domain (e.g., an unstopped SITL instance, stray test runner, or misconfigured daemon) but remains idle or silent during the capture window, it generates **zero** samples in the raw log.
   - Observing 100% of samples from a single GID proves **Sample-Origin Homogeneity (单写端样本一致性)** for transmitted packets; it **CANNOT** prove **Full-Graph Publisher Exclusivity (全图发布者独占性)**.
   - True publisher exclusivity is a graph-topology property that requires active discovery verification (`get_publishers_info_by_topic`), asserting `len(publishers) == 1` across the network domain throughout the session lifecycle.
2. **GuidPrefix Match $\ne$ Direct Writer Endpoint Binding**:
   - In standard RTPS (OMG formal/2019-04-03 Section 8.2), a 16/24-byte GUID consists of a 12-byte `GuidPrefix_t` (identifying the Participant / ROS Node context) and a 4-byte `EntityId_t` (identifying the specific DataWriter or DataReader).
   - Reconciling the 12-byte `GuidPrefix` of native target samples with the `GuidPrefix` of reader endpoints in [`initialized.json`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/40-aruco-tracking-10/run/epochs/e77b1ed46ede49d68e2e68edddc3fd25/tasks/5a474c596d1647c7995ec93427fdc417/px4/initialized.json) proves shared participant provenance (i.e. both were created under the same ROS2 node context).
   - However, because no DataWriter discovery snapshot was taken for native target topics, there is **no direct discovery record in evidence asserting that `wksim_joint_<stack>_control` owns writer endpoint `00001403`, `00001503`, or `00001c03`**.
   - Therefore, the binding status is classified strictly as **`participant_guid_prefix_matched_writer_unbound`**, and full-graph exclusivity is classified as **`unverified_passive_observation_only`**. Fabricating a "pass" or asserting "exclusive" is strictly prohibited.

---

## 2. Empirical Findings from Preserved Successful Runs

### 2.1 Run 10 (PX4 Tracking Candidate)

- **Capture Root**: `validation/40-aruco-tracking-10/run/epochs/e77b1ed46ede49d68e2e68edddc3fd25/tasks/5a474c596d1647c7995ec93427fdc417`
- **Selected Flight Stack**: `px4` (UAV 2)

#### Detailed DDS Channel & GID Breakdown:

| Channel / Topic | Category | Samples | Observed Publisher GID | RTPS GuidPrefix (12B) | Entity ID | Entity Kind |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/wksim_px4_21/fmu/in/trajectory_setpoint` | **native_target** | 1,281 | `010f7f014b267c240000000000001c030000000000000000` | `010f7f014b267c2400000000` | `00001c03` | DataWriter (`0x03`) |
| `/wksim_px4_21/fmu/in/vehicle_command` | **native_target** | 6 | `010f7f014b267c240000000000001a030000000000000000` | `010f7f014b267c2400000000` | `00001a03` | DataWriter (`0x03`) |
| `/uav2/prometheus/v2/state` | public_control | 15,646 | `010f7f014b267c2400000000000022030000000000000000` | `010f7f014b267c2400000000` | `00002203` | DataWriter (`0x03`) |
| `/uav2/prometheus/text_info` | public_control | 115 | `010f7f014b267c2400000000000020030000000000000000` | `010f7f014b267c2400000000` | `00002003` | DataWriter (`0x03`) |
| `/uav2/prometheus/v2/command` | public_command | 89 | `010f7f0157260e4f00000000000016030000000000000000` | `010f7f0157260e4f00000000` | `00001603` | DataWriter (Task runner) |
| `/uav2/prometheus/v2/setup` | public_command | 4 | `010f7f0157260e4f00000000000015030000000000000000` | `010f7f0157260e4f00000000` | `00001503` | DataWriter (Task runner) |
| `/wksim_px4_21/fmu/out/vehicle_local_position_v1` | native_telemetry | 3,890 | `010f7f014926051e0000000000003a030000000000000000` | `010f7f014926051e00000000` | `00003a03` | DataWriter (PX4 FC) |
| `/wksim_px4_21/fmu/out/vehicle_status_v1` | native_telemetry | 164 | `010f7f014926051e0000000000003c030000000000000000` | `010f7f014926051e00000000` | `00003c03` | DataWriter (PX4 FC) |
| `/wksim_px4_21/fmu/out/vehicle_control_mode` | native_telemetry | 165 | `010f7f014926051e00000000000036030000000000000000` | `010f7f014926051e00000000` | `00003603` | DataWriter (PX4 FC) |

#### Cross-Evidence Reconciliation:
1. **Participant Matching with `px4/initialized.json`**:
   - Reader on `/uav2/prometheus/v2/setup` for `wksim_joint_px4_control`: `010f7f014b267c240000000000002304...`
   - Reader on `/uav2/prometheus/v2/command` for `wksim_joint_px4_control`: `010f7f014b267c240000000000002404...`
   - **GuidPrefix Match**: Exactly matches `010f7f014b267c2400000000` across all native target samples!
2. **Process Identity in `children.json`**:
   - Process `px4-control` (PID 9803) was launched with arguments `--ros-args ... -r __node:=wksim_joint_px4_control`.
3. **Control Log in `px4-control.log`**:
   - Line 9 records `scene_native_sources_bound` binding incoming telemetry sources (`native_endpoints` has `/wksim_px4_21/fmu/out/*` matching `010f7f014926051e00000000...`).
   - Outgoing target publisher GIDs (`trajectory_setpoint`) are **NOT** logged anywhere in `px4-control.log`.

---

### 2.2 Run 13-ap (ArduCopter Tracking Candidate)

- **Capture Root**: `validation/40-aruco-tracking-13-ap/run/epochs/3662bc056ae74e0abed662214a8010bd/tasks/8ba1823783dd458fbda33a51e08d2a8c`
- **Selected Flight Stack**: `arducopter` (UAV 1)

#### Detailed DDS Channel & GID Breakdown:

| Channel / Topic | Category | Samples | Observed Publisher GID | RTPS GuidPrefix (12B) | Entity ID | Entity Kind |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/ap/cmd_gps_pose` | **native_target** | 857 | `010f7f01f624c70700000000000014030000000000000000` | `010f7f01f624c70700000000` | `00001403` | DataWriter (`0x03`) |
| `/ap/cmd_vel` | **native_target** | 637 | `010f7f01f624c70700000000000015030000000000000000` | `010f7f01f624c70700000000` | `00001503` | DataWriter (`0x03`) |
| `/uav1/prometheus/v2/state` | public_control | 15,802 | `010f7f01f624c70700000000000020030000000000000000` | `010f7f01f624c70700000000` | `00002003` | DataWriter (`0x03`) |
| `/uav1/prometheus/text_info` | public_control | 111 | `010f7f01f624c7070000000000001e030000000000000000` | `010f7f01f624c70700000000` | `00001e03` | DataWriter (`0x03`) |
| `/uav1/prometheus/v2/command` | public_command | 88 | `010f7f010525a40500000000000016030000000000000000` | `010f7f010525a40500000000` | `00001603` | DataWriter (Task runner) |
| `/uav1/prometheus/v2/setup` | public_command | 4 | `010f7f010525a40500000000000015030000000000000000` | `010f7f010525a40500000000` | `00001503` | DataWriter (Task runner) |
| `/ap/wksim/local_state_v1` | native_telemetry | 3,730 | `010f7f01f424791800000000000013030000000000000000` | `010f7f01f424791800000000` | `00001303` | DataWriter (AP FC) |
| `/ap/status` | native_telemetry | 156 | `010f7f01f42479180000000000000e030000000000000000` | `010f7f01f424791800000000` | `00000e03` | DataWriter (AP FC) |

#### Cross-Evidence Reconciliation:
1. **Participant Matching with `arducopter/initialized.json`**:
   - Reader on `/uav1/prometheus/v2/setup` for `wksim_joint_arducopter_control`: `010f7f01f624c7070000000000002104...`
   - Reader on `/uav1/prometheus/v2/command` for `wksim_joint_arducopter_control`: `010f7f01f624c7070000000000002204...`
   - **GuidPrefix Match**: Exactly matches `010f7f01f624c70700000000` across all native target samples!
2. **Process Identity in `children.json`**:
   - Process `arducopter-control` (PID 9462) was launched with arguments `--ros-args ... -r __node:=wksim_joint_arducopter_control`.
3. **Control Log in `arducopter-control.log`**:
   - Line 5 records `scene_native_sources_bound` binding incoming telemetry sources (`/ap/status` and `/ap/wksim/local_state_v1` matching `010f7f01f424791800000000...`).
   - Outgoing target publisher GIDs (`cmd_gps_pose`, `cmd_vel`) are **NOT** logged anywhere in `arducopter-control.log`.

---

## 3. The 4 Architectural Gaps

| Gap ID | Gap Title | Root Cause in Codebase | Concrete Evidence Impact |
| :--- | :--- | :--- | :--- |
| **GAP-01** | **Missing Target Publisher Discovery Snapshot** | `aruco_joint_task.py:request_graph_ready()` queries `get_subscriptions_info_by_topic()` only for `/setup` and `/command`. It never calls `get_publishers_info_by_topic()` for native targets. | `initialized.json` retains reader discovery for public commands, but 0 writer discovery records for `/ap/cmd_vel`, `/ap/cmd_gps_pose`, or `trajectory_setpoint`. |
| **GAP-02** | **Passive Trace Observation Inadequate for Exclusivity** | `aruco_raw_capture.py` is a passive subscriber (`take()`). It samples received packets, not DDS participant domain existence. | Single GID in raw packets proves all *received* packets came from one writer, but cannot detect dormant or silent secondary writers on the domain. |
| **GAP-03** | **Control Node Target Publisher Self-Attestation Absent** | `prometheus_control/node.py` logs `scene_native_sources_bound` only for `self.native.subscriptions`. It does not query or log local writer GIDs for `self.target_pub` or `self.velocity_pub`. | Control node cannot independently self-attest its own target publisher endpoint GID in `*-control.log`. |
| **GAP-04** | **Absence of Continuous / Boundary Discovery Verification** | No graph discovery check is performed at session close or mid-flight. | Mid-session rogue publisher attachment or network partition cannot be ruled out offline. |

---

## 4. Minimal Capture Design (最小采集设计)

To bridge these exact gaps in future runs with negligible runtime overhead, the following minimal additions are specified:

```
                  +-------------------------------------------------------------+
                  |                      Session Start                          |
                  |  aruco_joint_task.py: request_graph_ready()                 |
                  |  - Query get_publishers_info_by_topic(target_topic)         |
                  |  - Assert len(publishers) == 1                              |
                  |  - Record native_request_graph in initialized.json          |
                  +-------------------------------------------------------------+
                                                 |
                                                 v
                  +-------------------------------------------------------------+
                  |                   Control Node Launch                       |
                  |  prometheus_control/node.py: init                           |
                  |  - Query local writer GIDs for target publishers            |
                  |  - Emit 'scene_native_targets_bound' in *-control.log       |
                  +-------------------------------------------------------------+
                                                 |
                                                 v
                  +-------------------------------------------------------------+
                  |                       Session Close                         |
                  |  aruco_joint_task.py: close()                               |
                  |  - Re-query get_publishers_info_by_topic(target_topic)        |
                  |  - Assert len(publishers) == 1 (no endpoint drift/fork)     |
                  |  - Record close discovery snapshot in result.json           |
                  +-------------------------------------------------------------+
                                                 |
                                                 v
                  +-------------------------------------------------------------+
                  |                       Offline Audit                         |
                  |  tools/audit_aruco_publishers.py                            |
                  |  - Assert: sample.publisher_gid == discovery.endpoint_gid   |
                  |            == control_log.endpoint_gid                      |
                  |  - Grant 'exclusive_and_bound' only when all 3 match        |
                  +-------------------------------------------------------------+
```

### Concrete Specifications:

1. **REQ-01: Session Init Target Discovery Snapshot**:
   - In `Simulator/wksim_runtime/aruco_joint_task.py:request_graph_ready()`:
     ```python
     native_graph = {}
     for topic in self.native_target_topics:
         pubs = self.node.get_publishers_info_by_topic(topic)
         if len(pubs) != 1 or pubs[0].node_name != expected_control_node:
             return False
         native_graph[topic] = {
             "publisher_count": 1,
             "node_name": pubs[0].node_name,
             "node_namespace": pubs[0].node_namespace,
             "endpoint_gid": bytes(pubs[0].endpoint_gid).hex(),
         }
     self.aruco_native_request_graph = native_graph
     ```
   - Persist `native_request_graph` into `initialized.json`.

2. **REQ-02: Session Close Boundary Discovery Verification**:
   - In `aruco_joint_task.py:close()`:
     - Re-query `get_publishers_info_by_topic` for all native target channels before teardown.
     - Verify that `publisher_count` remained exactly 1 and `endpoint_gid` did not change.
     - Persist the close snapshot into `result.json`.

3. **REQ-03: Control Node Target Publisher Self-Attestation**:
   - In `ros2/src/prometheus_control/prometheus_control/node.py`:
     - After creating native target publishers, query local writer GIDs via RMW/DDS and emit:
       ```json
       {"event": "scene_native_targets_bound", "native_target_endpoints": {"/ap/cmd_vel": "...", "/ap/cmd_gps_pose": "..."}}
       ```
     - Emitted into `*-control.log`.

4. **REQ-04: Offline Three-Way Equality Verification**:
   - In `tools/audit_aruco_publishers.py`:
     - Cross-check:
       $$\text{Sample GID} = \text{Init Discovery GID} = \text{Control Log GID}$$
     - Verify both init and close discovery snapshots record `publisher_count == 1`.
     - Only when this tripartite agreement and boundary invariance are satisfied may `exclusive_and_bound` be certified.

---

## 5. Tooling & Verification Suite

The audit logic and assertions are implemented in:
- [`tools/audit_aruco_publishers.py`](file:///C:/Users/PC/Documents/odid编译/wksim/tools/audit_aruco_publishers.py): Read-only offline analyzer.
- [`validation/test_aruco_publishers.py`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/test_aruco_publishers.py): Unit and integration test suite.

### CLI Usage:
```bash
# Audit a specific run (e.g. Run 10 PX4)
python3 tools/audit_aruco_publishers.py --run-root validation/40-aruco-tracking-10 --output report-10.json

# Audit Run 13-ap
python3 tools/audit_aruco_publishers.py --run-root validation/40-aruco-tracking-13-ap --output report-13.json
```
- `--output` is opened strictly in `'x'` mode (refuses overwrite; raises `FileExistsError`).
- Output JSON strictly prohibits IEEE `NaN` and `Infinity` tokens (`allow_nan=False`).

### Test Execution Results:

```text
wsl -d Ubuntu-22.04 bash -c "cd /mnt/c/Users/PC/Documents/odid编译/wksim && python3 -m unittest validation/test_aruco_publishers.py"

Ran 10 tests in 1.739s
OK
```

All 10 tests pass across Windows and WSL environments:
- `test_parse_guid_standard_rtps`: Passed.
- `test_parse_guid_invalid_formats`: Passed.
- `test_sanitize_no_nan`: Passed.
- `test_passive_single_gid_refuses_full_graph_exclusivity`: Passed.
- `test_multiple_gids_detected_as_conflicting`: Passed.
- `test_guid_prefix_match_retains_writer_unbound`: Passed.
- `test_guid_prefix_mismatch_detected`: Passed.
- `test_exclusive_output_mode_rejected_on_existing`: Passed.
- `test_real_evidence_tracking_10`: Passed.
- `test_real_evidence_tracking_13_ap`: Passed.
