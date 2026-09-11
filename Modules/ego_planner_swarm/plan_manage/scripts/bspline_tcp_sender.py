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
tested off-robot.  All ROS imports (``rospy``, the message class) and the socket
send loop are confined to :func:`main`.

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
    encoder = BsplineTcpEncoder(session_id)

    sock = socket.create_connection((host, port))

    def on_bspline(message):
        try:
            sock.sendall(encode_bspline_frame(encoder, message))
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

    rospy.Subscriber(topic, TrajUtilsBspline, on_bspline, queue_size=10)
    rospy.loginfo("Streaming %s -> tcp://%s:%d (session %s)", topic, host, port, session_id)
    rospy.spin()


if __name__ == "__main__":
    main()
