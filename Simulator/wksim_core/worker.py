"""One generated Model per OS process; strict newline-delimited JSON RPC.

Derived from tools/probe_joint_clock.py's worker/step/snapshot loop. The parent
must exclusively own these pipes from launch, with one outstanding RPC. On an
RPC failure it must retire the child through its lifecycle owner (no retries).
"""
import argparse
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
    if (set(request) != {'version', 'epoch', 'tick', 'commands'}
            or type(request['tick']) is not int or request['tick'] != current_tick + 1):
        raise ValueError('Expected exactly the next authoritative tick')
    commands = request['commands']
    if (not isinstance(commands, list) or len(commands) != 16
            or any(not _number(x) or not 0 <= x <= 1 for x in commands)):
        raise ValueError('Expected 16 finite non-bool commands in [0,1]')
    return commands


def validate_response(response, epoch, tick):
    _header(response, epoch)
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


def model_worker(library, trace, epoch):
    """Run exactly one Model; EOF closes normally, invalid input raises."""
    global _started
    _epoch(epoch)
    if _started:
        raise RuntimeError('Only one Model lifetime is allowed per worker process')
    _started = True
    with Path(trace).open('x', encoding='utf-8', buffering=1) as log, Model(library) as model:
        state = None
        while True:
            line = sys.stdin.readline(REQUEST_LIMIT + 1)
            if not line:
                return
            request = parse_frame(line, REQUEST_LIMIT)
            commands = step_request(request, model.ticks, epoch)
            if commands is not None:
                state = model.step(commands)
            response = dict(version=1, epoch=epoch, tick=model.ticks, state=state)
            if commands is not None:
                # Preserve the exact accepted input, as well as decoded fields.
                log.write(encoded(dict(**response, commands=commands, input=line,
                                       request=request)) + '\n')
            validate_response(response, epoch, model.ticks)
            output = encoded(response) + '\n'
            if len(output.encode('utf-8')) > RESPONSE_LIMIT:
                raise ValueError('Oversized response')
            sys.stdout.write(output)
            sys.stdout.flush()


def receive_worker(child, request, epoch, timeout=3.0):
    """Bound the entire RPC, including partial lines, by a wall-clock deadline.

    3s is an experimental default, not an approved production threshold.
    Linux nonblocking pipes avoid a new thread for every 1ms model step. No
    other reader/writer may use these pipes while an RPC is outstanding. A
    timed-out channel stays poisoned until the lifecycle owner retires it.
    """
    if not _number(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    if sys.platform != 'linux':
        raise RuntimeError('Model worker transport requires WSL/Linux')
    deadline = time.monotonic() + timeout
    with _rpc_guard:
        if not hasattr(child, '_wksim_rpc'):
            child._wksim_rpc = dict(lock=threading.Lock(), failed=False, tick=0, epoch=epoch)
        rpc = child._wksim_rpc
    if not rpc['lock'].acquire(blocking=False):
        raise RuntimeError('Only one outstanding worker RPC is allowed')
    try:
        if rpc['failed'] or rpc['epoch'] != epoch:
            raise RuntimeError('Worker channel must be retired')
        commands = step_request(request, rpc['tick'], epoch)
        frame = encoded(request) + '\n'
        parse_frame(frame, REQUEST_LIMIT)
        reader, writer = child.stdout.fileno(), child.stdin.fileno()
        os.set_blocking(reader, False)
        os.set_blocking(writer, False)

        def ready(reading):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Model worker response timeout; retire child')
            readable, writable, _ = select.select([reader] if reading else [],
                                                   [] if reading else [writer], [], remaining)
            if not (readable or writable):
                raise TimeoutError('Model worker response timeout; retire child')

        try:
            outgoing = memoryview(frame.encode('utf-8'))
            while outgoing:
                ready(False)
                try:
                    written = os.write(writer, outgoing)
                except BlockingIOError:
                    continue
                if written == 0:
                    raise RuntimeError('Worker request pipe closed')
                outgoing = outgoing[written:]
            incoming = bytearray()
            while b'\n' not in incoming:
                ready(True)
                try:
                    chunk = os.read(reader, min(4096, RESPONSE_LIMIT+1-len(incoming)))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise RuntimeError('Worker exited without a complete response')
                incoming.extend(chunk)
                if len(incoming) > RESPONSE_LIMIT:
                    raise ValueError('Oversized worker response')
            tick = rpc['tick'] + (commands is not None)
            response = validate_response(parse_frame(incoming.decode('utf-8'), RESPONSE_LIMIT), epoch, tick)
            if time.monotonic() >= deadline:
                raise TimeoutError('Model worker response timeout; retire child')
            rpc['tick'] = tick
            return response
        except Exception:
            rpc['failed'] = True
            raise
    finally:
        rpc['lock'].release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--epoch', required=True)
    args = parser.parse_args()
    model_worker(args.library, args.trace, args.epoch)
