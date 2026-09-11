#!/usr/bin/env python3
"""Read-only ROS1 relay from traj_utils/Bspline to prometheus_msgs/Bspline.

The relay is deliberately limited to the planner trajectory message.  It does
not allocate a trajectory ID, add an epoch, publish a command, or subscribe to
the legacy Prometheus command topic.  The next hop (an external ros1_bridge)
can then map the same-package ROS1 prometheus_msgs/Bspline to the ROS2 message.
"""

import copy


BSPLINE_FIELDS = (
    "drone_id",
    "order",
    "traj_id",
    "start_time",
    "knots",
    "pos_pts",
    "yaw_pts",
    "yaw_dt",
)
DEFAULT_UAV_ID = 1
DEFAULT_INPUT_TOPIC = "/uav{uav_id}/planning/bspline"
DEFAULT_OUTPUT_TOPIC = "/uav{uav_id}/planning/bspline_ros1_prometheus"


def relay_topics(uav_id=DEFAULT_UAV_ID):
    """Return the public EGO input and private ROS1 relay output topics."""
    if type(uav_id) is not int or uav_id < 1:
        raise ValueError("uav_id must be a positive integer")
    return (
        DEFAULT_INPUT_TOPIC.format(uav_id=uav_id),
        DEFAULT_OUTPUT_TOPIC.format(uav_id=uav_id),
    )


def copy_bspline_fields(source, target):
    """Copy only the Bspline schema without mutating ``source`` or minting IDs.

    The ROS1 ``time`` value is copied as-is.  Clock-domain normalization belongs
    to the reviewed ROS2 ingress contract; this relay must not rewrite it.
    """
    missing = next((field for field in BSPLINE_FIELDS if not hasattr(source, field)), None)
    if missing is not None:
        raise ValueError("missing Bspline field: " + missing)
    for field in BSPLINE_FIELDS:
        setattr(target, field, copy.deepcopy(getattr(source, field)))
    return target


def main():
    # Keep ROS imports inside main so the schema/immutability contract is testable
    # on a machine without ROS1 installed.
    import rospy
    from prometheus_msgs.msg import Bspline as PrometheusBspline
    from traj_utils.msg import Bspline as TrajUtilsBspline

    rospy.init_node("bspline_ros1_relay")
    uav_id = rospy.get_param("~uav_id", DEFAULT_UAV_ID)
    default_input, default_output = relay_topics(uav_id)
    input_topic = rospy.get_param("~input_topic", default_input)
    output_topic = rospy.get_param("~output_topic", default_output)
    publisher = rospy.Publisher(output_topic, PrometheusBspline, queue_size=10)

    def on_bspline(message):
        try:
            converted = copy_bspline_fields(message, PrometheusBspline())
            publisher.publish(converted)
        except Exception as error:  # malformed relay input produces no output
            rospy.logerr_throttle(1.0, "Bspline relay rejected input: %s", error)

    rospy.Subscriber(input_topic, TrajUtilsBspline, on_bspline, queue_size=10)
    rospy.loginfo("Relaying %s -> %s", input_topic, output_topic)
    rospy.spin()


if __name__ == "__main__":
    main()
