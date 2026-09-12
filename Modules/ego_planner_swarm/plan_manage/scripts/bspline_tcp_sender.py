#!/usr/bin/env python3
"""ROS1 -> pinned-TCP-envelope sender for the #102 Route-B Bspline transport.

This node is the ROS1 (Noetic) origin of the offline Route-B transport: it
subscribes to the EGO planner's Bspline output and streams each message as a
pinned ``wksim.bspline-tcp-envelope.v1`` frame over TCP to a pure-Python receiver
(``Simulator/wksim_runtime/planner_transport_receiver.py``).  It is the send-side
counterpart of the committed ``bspline_ros1_relay.py`` and shares its discipline:

- it copies ONLY the eight Bspline schema fields and never mints a trajectory id,
  run id, epoch, or any other identifier;
- it passes ``start_time`` through UNCHANGED (no nanosecond flattening, no
  offset, no clock-domain rewrite).  Clock-domain normalization belongs to the
  receiver's admission bridge; this sender must not rewrite it.  The ROS1
  ``secs``/``nsecs`` form is preserved on the wire and flattened to integer
  nanoseconds only by the receiving decoder;
- a malformed message produces NO frame (fail-closed).

The field-extraction and frame-encoding core (``build_payload`` /
``encode_bspline_frame``) is pure and importable without ROS so it can be unit
tested off-robot. ROS imports and socket creation are confined to :func:`main`;
``OrderedFrameSender`` serializes encoding/writes on an injected connection.

Explicit ``~accept_control=true`` adds the upstream Bool output gate and
private ``~hold``/``~cancel`` Empty inputs on the same sequence stream. The
Bool is never treated as cancellation. These are requests with no transport
ACK; a sent cancel does not prove that a flight controller stopped.

Cross-distro import reality (honest): this script lives OUTSIDE the ``Simulator``
package (the ``Modules`` tree is a PEP 420 namespace, not an installed package),
so it inserts the repository root -- derived from ``__file__`` -- onto
``sys.path`` before importing the committed envelope module.  The envelope
re-verifies the pinned ROS1/ROS2 ``Bspline.msg`` hashes from that same repository
at encoder construction, so this script must run against a real checkout of this
repository (in the Noetic WSL distro that is the mounted Windows repo, e.g.
``/mnt/c/.../wksim``).  It does NOT install or vendor anything.
"""
from pathlib import Path
import sys
import threading

# This script is not inside the Simulator package; make the repository importable
# whether it is launched via rosrun, python3, or imported by a test.  Idempotent.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Simulator.wksim_runtime.bspline_tcp_envelope import (
    BSPLINE_PAYLOAD_FIELDS,
    BsplineEnvelopeError,
    BsplineTcpEncoder,
)

# Single source of truth for the eight-field schema (drone_id, order, traj_id,
# start_time, knots, pos_pts, yaw_pts, yaw_dt).
BSPLINE_FIELDS = BSPLINE_PAYLOAD_FIELDS

DEFAULT_UAV_ID = 1
DEFAULT_INPUT_TOPIC = "/uav{uav_id}/planning/bspline"
DEFAULT_RECEIVER_HOST = "127.0.0.1"
DEFAULT_RECEIVER_PORT = 29700


def input_topic(uav_id=DEFAULT_UAV_ID):
    """Return the EGO planner Bspline output topic for one UAV."""
    if type(uav_id) is not int or uav_id < 1:
        raise ValueError("uav_id must be a positive integer")
    return DEFAULT_INPUT_TOPIC.format(uav_id=uav_id)


def build_payload(message):
    """Extract the eight Bspline fields from a ROS message into an encoder payload.

    Pure and ROS-less: ``message`` is any object exposing the eight Bspline
    attributes (e.g. ``traj_utils/Bspline`` or ``prometheus_msgs/Bspline``).
    ``start_time`` is passed through verbatim -- the encoder accepts a
    ``sec``/``nanosec`` or a ROS1 ``secs``/``nsecs`` time object -- so no clock
    value is flattened, offset, or rebased here, and ``traj_id`` is copied
    unchanged.  No identifier is minted.  Raises ValueError if a field is
    missing; the encoder then enforces exact types and ranges.
    """
    missing = next((field for field in BSPLINE_FIELDS if not hasattr(message, field)), None)
    if missing is not None:
        raise ValueError("missing Bspline field: " + missing)
    return {
        "drone_id": message.drone_id,
        "order": message.order,
        "traj_id": message.traj_id,
        "start_time": message.start_time,        # verbatim; never rewritten
        "knots": list(message.knots),
        "pos_pts": list(message.pos_pts),        # elements keep their x/y/z
        "yaw_pts": list(message.yaw_pts),
        "yaw_dt": message.yaw_dt,
    }


def encode_bspline_frame(encoder, message):
    """Encode one ROS Bspline message into a pinned TCP frame (pure, ROS-less).

    ``encoder`` is a committed ``BsplineTcpEncoder`` bound to the shared
    ``transport_session_id``; its sequence high-water advances only on a fully
    serialized + framed success.  Returns the length-prefixed wire bytes.
    """
    if not isinstance(encoder, BsplineTcpEncoder):
        raise ValueError("encoder must be a BsplineTcpEncoder")
    return encoder.encode_frame(build_payload(message))


class OrderedFrameSender:
    """Serialize callback encoding and writes on one owned connection.

    Wire order is lock acquisition order, not a promise about ROS ordering
    across different topics. A write failure retires the connection; a sent
    terminal cancel suppresses later output until a new sender is constructed.
    """
    def __init__(self, encoder, connection, *, accept_control=False):
        if not isinstance(encoder, BsplineTcpEncoder):
            raise ValueError("encoder must be a BsplineTcpEncoder")
        if type(accept_control) is not bool:
            raise ValueError("accept_control must be a strict bool")
        if not all(callable(getattr(connection, name, None)) for name in ("sendall", "shutdown", "close")):
            raise ValueError("connection must support sendall/shutdown/close")
        self.encoder, self.connection = encoder, connection
        self.accept_control = accept_control
        self._lock = threading.Lock()
        self._closed = False
        self._cancel_sent = False

    def _close_socket(self):
        import socket
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()

    def close(self):
        # Interrupt a blocked send before waiting for its encoding/write lock.
        self._closed = True
        self._close_socket()
        with self._lock:
            pass

    def _send(self, encode):
        if self._closed:
            raise OSError("sender connection is closed")
        if self._cancel_sent:
            return False
        frame = encode()
        try:
            self.connection.sendall(frame)
        except OSError:
            self._closed = True
            self._close_socket()
            raise
        return True

    def send_bspline(self, message):
        with self._lock:
            return self._send(lambda: encode_bspline_frame(self.encoder, message))

    def send_control(self, control):
        if not self.accept_control:
            raise ValueError("control frames require explicit accept_control")
        with self._lock:
            sent = self._send(lambda: self.encoder.encode_control_frame(control))
            if sent and control["kind"] == "cancel":
                self._cancel_sent = True
            return sent


def main():
    # ROS imports are confined here so the conversion core stays ROS-less and
    # unit-testable on a machine without ROS1 installed.
    import socket

    import rospy
    from traj_utils.msg import Bspline as TrajUtilsBspline

    rospy.init_node("bspline_tcp_sender")
    uav_id = rospy.get_param("~uav_id", DEFAULT_UAV_ID)
    topic = rospy.get_param("~input_topic", input_topic(uav_id))
    host = rospy.get_param("~receiver_host", DEFAULT_RECEIVER_HOST)
    port = int(rospy.get_param("~receiver_port", DEFAULT_RECEIVER_PORT))
    # Required, no default: the shared transport session id.  The encoder
    # validates its format and re-pins both message hashes at construction.
    session_id = rospy.get_param("~transport_session_id")
    accept_control = rospy.get_param("~accept_control", False)
    if type(accept_control) is not bool:
        raise ValueError("accept_control must be a strict bool")
    if accept_control and uav_id != 1:
        raise ValueError("control transport currently supports the reviewed uav1 profile only")
    encoder = BsplineTcpEncoder(session_id)

    sock = socket.create_connection((host, port))
    if accept_control:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sender = OrderedFrameSender(encoder, sock, accept_control=accept_control)
    rospy.on_shutdown(sender.close)

    def transmit(operation):
        try:
            operation()
        except (BsplineEnvelopeError, ValueError) as error:
            # Malformed planner output is dropped fail-closed; no frame is sent.
            rospy.logerr_throttle(1.0, "Bspline TCP sender dropped a message: %s", error)
        except OSError as error:
            # The transport is fire-and-forget: there is NO ACK and NO in-band
            # way to learn of a receiver poison, so a dead connection cannot be
            # resumed on this session.  Restart both ends with a NEW shared
            # transport_session_id to recover.
            rospy.logerr(
                "Bspline TCP sender connection failed (no ACK/reconnect; restart "
                "with a NEW shared transport_session_id): %s", error)
            rospy.signal_shutdown("tcp connection failed")

    subscribers = []
    try:
        if accept_control:
            from std_msgs.msg import Bool, Empty
            gate_topic = rospy.get_param("~gate_topic", "/uav1/prometheus/command/ego_command_stop_pub")
            subscribers.append(rospy.Subscriber(
                gate_topic, Bool,
                lambda msg: transmit(lambda: sender.send_control({"kind": "gate", "open": msg.data})),
                queue_size=10))
            # These explicit wksim commands are distinct from EGO's output gate.
            subscribers.append(rospy.Subscriber(
                "~hold", Empty, lambda _msg: transmit(lambda: sender.send_control({"kind": "hold"})), queue_size=1))
            subscribers.append(rospy.Subscriber(
                "~cancel", Empty, lambda _msg: transmit(lambda: sender.send_control({"kind": "cancel"})), queue_size=1))
        subscribers.append(rospy.Subscriber(
            topic, TrajUtilsBspline, lambda msg: transmit(lambda: sender.send_bspline(msg)), queue_size=10))
        rospy.loginfo("Streaming %s -> tcp://%s:%d (session %s)", topic, host, port, session_id)
        rospy.spin()
    finally:
        for subscriber in subscribers:
            subscriber.unregister()
        sender.close()


if __name__ == "__main__":
    main()
