# Full OPS-05 — Network and remote-operation contract

Status: **defined, not implemented**. This is the bounded contract-definition slice for GitHub #156. Existing local isolation and same-host evidence are retained as partial evidence; they are not cross-host compatibility proof.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:73`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-05`, `followup_ids=[156]`.
- Related evidence: #13's independent PX4/AP runs and #19's same-host joint-scene runs. Their reports explicitly distinguish independent experiments, joint scenes and unverified cross-host operation.
- `Simulator/wksim_runtime/isolation.py` reserves network/IPC/mount boundaries, `/dev/shm`, run/vehicle/ROS/native identities and pinned local ports. `config.py` validates absolute WSL paths, distinct sockets and a bounded loopback GCS forward.
- `tools/run-wksim.sh` creates a private network namespace and starts the formal runtime. The current accepted profile is local WSL native DDS; no remote-host transport, authentication or distributed clock contract is accepted.

## Atomic scope

| ID | Network capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-05-A | UDP broadcast/discovery | `blocked`: no source-backed broadcast scope or discovery lifecycle is owned | Address family, broadcast scope, message identity, discovery timeout/retry and refusal outside the allowed network |
| OPS-05-B | Designated host/unicast | `partial`: loopback forwarding and explicit local paths are bounded; remote host behavior is not tested | Host allowlist, route/MTU assumptions, failure/reconnect policy and end-to-end source/receive evidence |
| OPS-05-C | JSON online link | `partial`: local HTTP/TCP/JSON surfaces exist with strict body/CSRF/identity checks; no remote JSON contract is accepted | Versioned framing, authentication, replay/epoch rules, timeout and backward-compatibility behavior |
| OPS-05-D | Port allocation | `partial`: fixed local ports and cooperative reservations are checked | Dynamic/declared port allocation, collision/rollback, IPv4/IPv6 scope and per-instance release evidence |
| OPS-05-E | Run and transport identity | `partial`: run ID, vehicle ID, namespace/domain, native IDs and output paths are recorded | Identity propagation across every packet, host and log plus foreign/duplicate/old packet rejection |
| OPS-05-F | Multiple same-host instances | `partial`: #13 proves one bounded independent PX4/AP pair; the full matrix is not complete | N instances, all resources and outputs isolated, one instance stopping/failing does not affect others |
| OPS-05-G | Cross-host/distributed operation | `blocked`: no approved remote host, security, clock, resource or recovery contract | Two-host run with source/receive timing, loss/reconnect, clock policy, cleanup and independently audited result |

## Transport and identity contract

Each network endpoint must be represented by a versioned manifest containing:

```text
run_id, instance_id, vehicle_id, scene/epoch, stack, protocol/version,
source_host, destination_host, address family, bind/advertise address,
port, namespace/domain, native identity, output root, timeout/retry policy
```

The manifest is input to admission, not an instruction to execute arbitrary network or shell commands. An endpoint is not accepted merely because a socket binds; the record must associate source/receive timestamps, epoch/sequence, message identity and the formal result.

### Scope and isolation rules

1. Independent runs have independent clocks, namespaces, identities, ports, output roots and process ownership. They must never be labelled as a joint scene.
2. A joint scene has one explicit authority-time/epoch policy. Network transport may be asynchronous, but it cannot silently become a second physics clock.
3. Remote operation must default deny. Only explicitly configured hosts/ports are allowed; missing authentication, address scope, route or identity evidence is a preflight rejection.
4. Foreign run/epoch/vehicle/sequence data is rejected before state mutation. Retries are idempotent only when the contract says so; they must not replay a motion command.
5. Stop, timeout and cleanup act only on the recorded process group and endpoint identity for that run. They do not kill a shared host service or another run.

### Failure semantics

Use distinct results for `accepted`, `bound`, `connected`, `timed_out`, `rejected_foreign`, `port_collision`, `host_not_allowed`, `authentication_failed`, `stale_epoch`, `transport_lost`, `remote_failed`, `cleanup_failed` and `completed`. A connection is not a native ACK, and a received JSON/UDP packet is not a physical action completion.

## Evidence-backed follow-up slices

These are proposed successors; this ticket adds no network transport or remote host behavior.

1. **Local identity/port matrix (owner: runtime maintainer):** reuse `isolation.py`, `config.py` and the formal entry to audit declared ports, namespaces, output paths and foreign/duplicate packets across a small same-host instance matrix.
2. **JSON link contract (owner: control/API maintainer):** freeze one framed JSON protocol with source/receive time, epoch, identity and replay rules. Keep the existing local-only HTTP security boundary; do not expose it remotely by changing a bind address.
3. **UDP discovery/unicast (owner: transport maintainer):** implement only after the broadcast and designated-host source contract is fixed. Add negative tests for scope, host allowlist, port collision and stale/foreign messages.
4. **Cross-host run (owner: integration maintainer):** requires explicit host/network authorization, clock and recovery decisions, and two isolated host resources. Record raw packets and both host identities; no current command is authorized by this definition ticket.

## Non-goals and preserved blockers

- No remote socket is opened, no broadcast is sent, and no host firewall/route/authentication is changed here.
- #13 and #19 remain scoped to their documented same-host independent/joint evidence; they do not close cross-host Full network behavior.
- The local-only console, private namespaces, DDS profile and no-arbitrary-command boundary remain unchanged.
- Hardware, vendor, rate and G6 decisions are unaffected. `full_complete` remains `false` for OPS-05 and for the project.
