"""One generated Model per OS process; strict newline-delimited JSON RPC.

Derived from tools/probe_joint_clock.py's worker/step/snapshot loop. The parent
must exclusively own these pipes from launch, with one outstanding RPC. On an
RPC failure it must retire the child through its lifecycle owner (no retries).
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import sys
import threading
import time

from .model import Model

REQUEST_LIMIT = 4096
RESPONSE_LIMIT = 65536
_started = False
_rpc_guard = threading.Lock()


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _async_evidence_identity(library, trace, epoch):
    library_path = Path(library).resolve(strict=True)
    trace_path = Path(trace).resolve(strict=True)
    return dict(
        epoch=epoch,
        truth_trace_sha256=_sha256_file(trace_path),
        model_library=str(library_path),
        model_library_sha256=_sha256_file(library_path),
    )


def _epoch(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise ValueError('Expected a 32 lower-case hex epoch')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def parse_frame(line, limit):
    if not line or not line.endswith('\n') or len(line.encode('utf-8')) > limit:
        raise ValueError('Missing newline or oversized JSON frame')
    return json.loads(line, object_pairs_hook=_pairs, parse_constant=_constant)


def _header(value, epoch):
    _epoch(epoch)
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('epoch') != epoch):
        raise ValueError('Invalid protocol version or stale epoch')


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def step_request(request, current_tick, epoch):
    """Validate before touching Model; None denotes a read-only snapshot."""
    _header(request, epoch)
    if set(request) == {'version', 'epoch', 'snapshot'} and request['snapshot'] is True:
        return None
    if (set(request) not in ({'version', 'epoch', 'tick', 'commands'},
                             {'version', 'epoch', 'tick', 'commands', 'terrain'})
            or type(request['tick']) is not int or request['tick'] != current_tick + 1):
        raise ValueError('Expected exactly the next authoritative tick')
    commands = request['commands']
    if (not isinstance(commands, list) or len(commands) != 16
            or any(not _number(x) or not 0 <= x <= 1 for x in commands)):
        raise ValueError('Expected 16 finite non-bool commands in [0,1]')
    if 'terrain' in request:
        terrain = request['terrain']
        if (not isinstance(terrain, list) or len(terrain) != 15
                or any(not _number(x) for x in terrain)):
            raise ValueError('Expected 15 finite non-bool terrain values')
    return commands


def initial_request(request, current_tick, epoch, *, initial_observed=False):
    """Validate an explicit one-shot initial-state request; None denies the shape.

    Any request carrying the 'initial' key is validated strictly here and never
    falls back to the snapshot or step paths. The request is read-only: both the
    parent channel tick and the child model ticks must still be zero.
    """
    if not isinstance(request, dict) or 'initial' not in request:
        return None
    _header(request, epoch)
    if set(request) != {'version', 'epoch', 'initial'} or request['initial'] is not True:
        raise ValueError('Expected an explicit initial-state request')
    if current_tick != 0:
        raise ValueError('Initial state is only available at tick zero')
    if initial_observed:
        raise ValueError('Initial state was already observed')
    return True


def terrain_request(request):
    """Extract validated terrain if present in request, else None."""
    if isinstance(request, dict) and 'terrain' in request:
        return list(request['terrain'])
    return None


def validate_response(response, epoch, tick):
    _header(response, epoch)
    if response.get('initial') is True:
        if (set(response) != {'version', 'epoch', 'tick', 'state', 'initial'}
                or type(response['tick']) is not int or response['tick'] != 0 or tick != 0):
            raise ValueError('Invalid initial-state response tick or fields')
        state = response['state']
        if (not isinstance(state, list) or len(state) != 120
                or any(not _number(x) for x in state)):
            raise ValueError('Invalid initial model state')
        return response
    if (set(response) != {'version', 'epoch', 'tick', 'state'}
            or type(response['tick']) is not int or response['tick'] < 0
            or response['tick'] != tick):
        raise ValueError('Invalid response tick or fields')
    state = response['state']
    if tick == 0 and state is None:
        return response
    if (tick == 0 or not isinstance(state, list) or len(state) != 120
            or any(not _number(x) for x in state)):
        raise ValueError('Invalid model state')
    return response


def model_worker(library, trace, epoch, *, async_evidence=False):
    """Run exactly one Model; EOF closes normally, invalid input raises."""
    global _started
    _epoch(epoch)
    if _started:
        raise RuntimeError('Only one Model lifetime is allowed per worker process')
    _started = True
    if async_evidence:
        from Simulator.wksim_runtime.evidence_stream import AsyncEvidenceStream
        log = AsyncEvidenceStream(trace, close_timeout=2)
    else:
        log = Path(trace).open('x', encoding='utf-8', buffering=1)
    if not async_evidence:
        return _worker_loop(library, log, epoch, async_evidence, trace)

    # _worker_loop owns the stream context, so reaching this branch means the
    # writer close completed successfully.  Refuse to publish an incomplete
    # sidecar even if a future stream implementation changes that contract.
    result = _worker_loop(library, log, epoch, async_evidence, trace)
    summary = log.summary()
    if (summary.get('complete') is not True
            or summary.get('alive') is not False
            or summary.get('closed') is not True
            or summary.get('error') is not None
            or summary.get('written_bytes') != summary.get('submitted_bytes')
            or (hasattr(os,'SCHED_OTHER') and summary.get('writer_scheduler') != dict(
                available=True,policy='SCHED_OTHER',priority=0,
                actual_policy=os.SCHED_OTHER,actual_priority=0))):
        raise RuntimeError('Async evidence writer did not close completely')

    # Hashes are intentionally computed only after the writer has retired.
    # Any path, digest, or read failure propagates without publishing evidence.
    summary.update(_async_evidence_identity(library, trace, epoch))
    with Path(str(trace)+'.writer.json').open('x', encoding='utf-8') as output:
        json.dump(summary, output, indent=2)
    return result


def _worker_loop(library, log, epoch, async_evidence, trace):
    with log, Model(library) as model:
        state = None
        initial_seen = False
        while True:
            line = sys.stdin.readline(REQUEST_LIMIT + 1)
            if not line:
                return
            if async_evidence:
                log.check()
            request = parse_frame(line, REQUEST_LIMIT)
            initial = initial_request(request, model.ticks, epoch, initial_observed=initial_seen)
            commands = None if initial else step_request(request, model.ticks, epoch)
            terrain = terrain_request(request)
            if initial:
                # Explicit one-shot read: never steps and never replaces the
                # snapshot state, which stays None at tick zero.
                if initial_seen:
                    raise ValueError('Initial state was already observed')
                initial_state = getattr(model, 'initial_state', None)
                if not callable(initial_state):
                    raise RuntimeError('Model lacks the explicit initial-state ABI')
                response = dict(version=1, epoch=epoch, tick=model.ticks,
                                state=initial_state(), initial=True)
                initial_seen = True
            else:
                if commands is not None:
                    if terrain is not None:
                        state = model.step(commands, terrain=terrain)
                    else:
                        state = model.step(commands)
                response = dict(version=1, epoch=epoch, tick=model.ticks, state=state)
            if commands is not None:
                # Preserve the exact accepted input, as well as decoded fields.
                response_json = encoded(response)
                extras = dict(commands=commands, input=line, request=request)
                if terrain is not None:
                    extras['terrain'] = terrain
                extras_json = encoded(extras)
                log.write(response_json[:-1] + ',' + extras_json[1:] + '\n')
                validate_response(response, epoch, model.ticks)
            elif initial:
                # Sidecar audit row; the main trace keeps its legacy step-only
                # shape so enumerate-from-tick-1 auditors stay valid unchanged.
                validate_response(response, epoch, model.ticks)
                response_json = encoded(response)
                extras_json = encoded(dict(input=line, request=request))
                with Path(str(trace) + '.initial.jsonl').open('x', encoding='utf-8') as audit:
                    audit.write(response_json[:-1] + ',' + extras_json[1:] + '\n')
            else:
                validate_response(response, epoch, model.ticks)
            output = (response_json if commands is not None or initial else encoded(response)) + '\n'
            if len(output.encode('utf-8')) > RESPONSE_LIMIT:
                raise ValueError('Oversized response')
            sys.stdout.write(output)
            sys.stdout.flush()


def receive_worker(child, request, epoch, timeout=3.0, *, health=None):
    """Single-channel compatibility API; see receive_workers for transport rules."""
    return receive_workers({0: (child, request)}, epoch, timeout, health=health)[0]


def receive_workers(requests, epoch, timeout=3.0, *, health=None):
    """Send every request before collecting responses under one wall deadline.

    Each channel permits one outstanding RPC. Its tick records the last actual
    validated response, even if another member fails. Any transport failure
    poisons the entire batch; only the caller can commit the common clock.
    """
    if not _number(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    if sys.platform != 'linux':
        raise RuntimeError('Model worker transport requires WSL/Linux')
    if not requests:
        raise ValueError('Expected at least one worker request')
    deadline = time.monotonic() + timeout
    channels = []
    transmitting = False
    try:
        # Complete validation and acquire every lock before sending any bytes.
        for name, (child, request) in requests.items():
            with _rpc_guard:
                if not hasattr(child, '_wksim_rpc'):
                    child._wksim_rpc = dict(lock=threading.Lock(), failed=False, tick=0, epoch=epoch,
                                            initial_observed=False)
                rpc = child._wksim_rpc
            if not rpc['lock'].acquire(blocking=False):
                raise RuntimeError('Only one outstanding worker RPC is allowed')
            channel = dict(name=name, rpc=rpc)
            channels.append(channel)
            if rpc['failed'] or rpc['epoch'] != epoch:
                raise RuntimeError('Worker channel must be retired')
            initial = initial_request(request, rpc['tick'], epoch,
                                      initial_observed=rpc.get('initial_observed', False))
            commands = None if initial else step_request(request, rpc['tick'], epoch)
            frame = encoded(request) + '\n'
            outgoing = frame.encode('utf-8')
            if len(outgoing) > REQUEST_LIMIT:
                raise ValueError('Missing newline or oversized JSON frame')
            channel.update(reader=child.stdout.fileno(), writer=child.stdin.fileno(),
                           outgoing=memoryview(outgoing), incoming=bytearray(),
                           tick=rpc['tick'] + (commands is not None))
        transmitting = True
        for channel in channels:
            os.set_blocking(channel['reader'], False)
            os.set_blocking(channel['writer'], False)
            channel['rpc'].update(request_tick=channel['tick'], sent_bytes=0, response_received=False)

        next_service = time.monotonic() + .02
        def ready(reading, pending):
            nonlocal next_service
            while True:
                now = time.monotonic()
                if health is not None and now >= next_service:
                    health()
                    now = time.monotonic()
                    next_service = now + .02
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError('Model worker response timeout; retire child')
                descriptors = [c['reader' if reading else 'writer'] for c in pending]
                readable, writable, _ = select.select(descriptors if reading else [],
                    [] if reading else descriptors, [],
                    min(remaining, max(0., next_service-now)) if health is not None else remaining)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model worker response timeout; retire child')
                if readable or writable:
                    return readable if reading else writable

        pending = list(channels)
        while pending:
            writable = ready(False, pending)
            for channel in pending[:]:
                if channel['writer'] not in writable:
                    continue
                try:
                    written = os.write(channel['writer'], channel['outgoing'])
                except BlockingIOError:
                    continue
                except BrokenPipeError:
                    raise RuntimeError('Worker request pipe closed')
                if written == 0:
                    raise RuntimeError('Worker request pipe closed')
                channel['rpc']['sent_bytes'] += written
                channel['outgoing'] = channel['outgoing'][written:]
                if not channel['outgoing']:
                    pending.remove(channel)
        responses = {}
        pending = list(channels)
        while pending:
            readable = ready(True, pending)
            for channel in pending[:]:
                if channel['reader'] not in readable:
                    continue
                incoming = channel['incoming']
                try:
                    chunk = os.read(channel['reader'], min(4096, RESPONSE_LIMIT + 1 - len(incoming)))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise RuntimeError('Worker exited without a complete response')
                incoming.extend(chunk)
                if len(incoming) > RESPONSE_LIMIT:
                    raise ValueError('Oversized worker response')
                if b'\n' not in incoming:
                    continue
                response = validate_response(parse_frame(incoming.decode('utf-8'), RESPONSE_LIMIT),
                                             epoch, channel['tick'])
                # Keep the actual confirmation frontier, distinct from clock.commit.
                channel['rpc'].update(tick=channel['tick'], response_received=True)
                if response.get('initial') is True:
                    channel['rpc']['initial_observed'] = True
                responses[channel['name']] = response
                pending.remove(channel)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model worker response timeout; retire child')
        return responses
    except BaseException:
        if transmitting:
            for channel in channels:
                channel['rpc']['failed'] = True
        raise
    finally:
        for channel in channels:
            channel['rpc']['lock'].release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--epoch', required=True)
    parser.add_argument('--async-evidence', action='store_true')
    args = parser.parse_args()
    model_worker(args.library, args.trace, args.epoch, async_evidence=args.async_evidence)
