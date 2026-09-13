"""One explicit operator home edit over the isolated native GCS interface.

This is a scenario actor, not an observer or a motion-command fallback. The
mission still uses the public DDS global entry. No retries or mode/arm commands
are emitted by this actor; the complete GCS packet exchange is retained.
"""
import json
import math
import socket
import time

from pymavlink.dialects.v20 import common as mavlink


class HomeMutation:
    def __init__(self, stack, directory, run_id):
        if stack not in ('px4', 'arducopter'): raise ValueError('Unsupported stack')
        self.system_id = 22 if stack == 'px4' else 241
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1', 14661 if stack == 'px4' else 14660))
        self.socket.setblocking(False)
        self.peer = self.request = self.ack = None
        self.log = (directory/'home-operator-wire.jsonl').open('x', buffering=1)
        self.run_id = run_id
        self.protocol = mavlink.MAVLink(self, srcSystem=246, srcComponent=190)

    def record(self, direction, raw, **fields):
        self.log.write(json.dumps(dict(run_id=self.run_id, direction=direction,
            monotonic_ns=time.monotonic_ns(), raw_hex=raw.hex(), **fields), allow_nan=False)+'\n')

    def write(self, raw):
        if self.peer is None: raise ValueError('Native GCS peer not observed')
        self.socket.sendto(raw, self.peer)
        self.record('out', bytes(raw), peer=list(self.peer))

    def poll(self):
        for _ in range(100):
            try: raw, peer = self.socket.recvfrom(65535)
            except BlockingIOError: break
            if peer[0] != '127.0.0.1': raise ValueError('Non-isolated GCS peer')
            self.record('in', raw, peer=list(peer))
            for message in self.protocol.parse_buffer(raw) or []:
                if message.get_srcSystem() != self.system_id or message.get_srcComponent() != 1:
                    continue
                if message.get_type() == 'HEARTBEAT':
                    if self.peer is not None and self.peer != peer: raise ValueError('Native GCS peer changed')
                    self.peer = peer
                if (self.request is not None and message.get_type() == 'COMMAND_ACK'
                        and message.command == mavlink.MAV_CMD_DO_SET_HOME):
                    if peer != self.peer: raise ValueError('Home ACK peer changed')
                    if message.result != mavlink.MAV_RESULT_ACCEPTED:
                        raise ValueError('Native home update rejected: '+str(message.result))
                    self.ack = message.to_dict()

    def change(self, home, *, altitude_delta_m=.1):
        if self.request is not None: raise ValueError('Only one native home edit per scenario')
        if self.peer is None: raise ValueError('Native GCS heartbeat required')
        values = (home['latitude_deg'], home['longitude_deg'], home['alt_amsl_m']+altitude_delta_m)
        if not all(type(v) in (float, int) and math.isfinite(v) for v in values):
            raise ValueError('Invalid native home coordinate')
        if altitude_delta_m != .1: raise ValueError('Frozen home mutation is +0.1 m AMSL')
        # Drain old responses before issuing the single, non-retried request.
        self.poll()
        self.request = dict(latitude_deg=values[0], longitude_deg=values[1], alt_amsl_m=values[2],
                            latitude_e7=int(values[0]*1e7), longitude_e7=int(values[1]*1e7),
                            command=179, issued_monotonic_ns=time.monotonic_ns())
        # COMMAND_INT preserves e7 coordinates; COMMAND_LONG float lat/lon
        # would introduce an unnecessary horizontal home shift.
        self.protocol.command_int_send(self.system_id, 1, mavlink.MAV_FRAME_GLOBAL,
            mavlink.MAV_CMD_DO_SET_HOME, 0, 0, 0., 0., 0., 0.,
            self.request['latitude_e7'], self.request['longitude_e7'], values[2])
        return dict(self.request)

    def close(self):
        self.socket.close()
        self.log.close()
