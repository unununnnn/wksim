"""Offline diagnostic: actual bridge can return normally without any Actor evidence."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Simulator.ue55.hex_bridge import binding, bridge

output = Path(__file__).with_name('empty-readback.jsonl')
expected = binding('hex-no-live-probe', 'a' * 32, 'sha256:' + 'b' * 64)
child = MagicMock()
child.__enter__.return_value = child
child.stdin = io.BytesIO()
child.stdout = io.BytesIO(b'{"packet":null,"relay_monotonic_s":1,"ended":true}\n')
udp = MagicMock()
udp.__enter__.return_value = udp
udp.recvfrom.side_effect = BlockingIOError
with patch('Simulator.ue55.hex_bridge.subprocess.Popen', return_value=child), \
     patch('Simulator.ue55.hex_bridge.socket.socket', return_value=udp):
    returned = bridge('/unused', '/unused/raw.jsonl', expected, 19060, output)
result = dict(scope='Offline mocked transport; no WSL child, UE, FC, ROS or flight',
              normal_return=True, return_value=returned, readback_bytes=output.stat().st_size,
              send_calls=udp.sendto.call_count,
              acceptance_assertion='normal bridge exit implies at least one Actor ACK',
              acceptance_assertion_passed=output.stat().st_size > 0)
Path(__file__).with_name('probe-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
# Intentional red: demonstrates why a caller must not promote bridge exit to LIVE acceptance.
assert result['acceptance_assertion_passed'], 'Normal bridge return has zero LIVE Actor ACKs'
