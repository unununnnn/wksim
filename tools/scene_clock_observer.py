"""Exercise a real ROS use_sim_time consumer; never publish flight commands."""
import errno
import time

from Simulator.wksim_runtime.scene_clock import ClockPublisher


class SceneClockObservation:
    def __init__(self, probe, clock):
        import rclpy
        from rclpy.parameter import Parameter
        self.ros, self.probe, self.clock = rclpy, probe, clock
        self.owner = self.reader = self.publisher = None
        self.samples, self.last_ns = 0, None
        self.first_ns = None
        self.duplicate_owner_rejected = False
        try:
            self.owner = rclpy.create_node('wksim_scene_clock_owner')
            self.publisher = ClockPublisher(self.owner)
            try:
                duplicate = ClockPublisher(self.owner)
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    raise
                self.duplicate_owner_rejected = True
            else:
                duplicate.close()
                raise RuntimeError('Duplicate cooperative scene clock owner was admitted')
            self.reader = rclpy.create_node('wksim_scene_clock_reader', parameter_overrides=[
                Parameter('use_sim_time', Parameter.Type.BOOL, True)])
            self.publish()
        except BaseException:
            self.close()
            raise

    def publish(self):
        self.publisher.publish(self.clock)
        self.probe.log('scene-clock', kind='publish', authority=self.clock.snapshot())

    def pump(self):
        self.ros.spin_once(self.reader, timeout_sec=0)
        clock = self.reader.get_clock()
        stamp = clock.now().nanoseconds
        if (not clock.ros_time_is_active or stamp % self.clock.STEP_NS
                or not 0 <= stamp <= self.clock.tick*self.clock.STEP_NS
                or self.last_ns is not None and stamp < self.last_ns):
            raise RuntimeError('Real ROS consumer clock is not on this scene timeline')
        if self.last_ns != stamp:
            self.samples += 1
            self.first_ns = stamp if self.first_ns is None else self.first_ns
            self.probe.log('scene-clock', kind='observe', ros_time_ns=stamp,
                           received_monotonic_ns=time.monotonic_ns())
        self.last_ns = stamp

    def at_boundary(self):
        # This is verification only; physics never waits on this consumer in advance().
        deadline = time.monotonic()+2
        while self.last_ns != self.clock.tick*self.clock.STEP_NS:
            self.pump()
            if time.monotonic() >= deadline:
                raise TimeoutError('ROS /clock consumer failed to observe pause boundary')
        return self.last_ns

    def report(self):
        return dict(samples=self.samples, first_ns=self.first_ns, last_ns=self.last_ns,
                    publisher_count=self.owner.count_publishers('/clock'),
                    publications=self.publisher.publications,
                    duplicate_owner_rejected=self.duplicate_owner_rejected,
                    consumer_use_sim_time=self.reader.get_parameter('use_sim_time').value,
                    ros_time_is_active=self.reader.get_clock().ros_time_is_active,
                    consumer_subscriptions=self.reader.get_subscriber_names_and_types_by_node(
                        self.reader.get_name(), self.reader.get_namespace()),
                    authority=self.clock.snapshot())

    def close(self):
        if self.reader is not None:
            self.reader.destroy_node()
            self.reader = None
        if self.publisher is not None:
            self.publisher.close()
            self.publisher = None
        if self.owner is not None:
            self.owner.destroy_node()
            self.owner = None
