# RC shared seam evidence

The current source test ran with the repository package path explicitly before
the installed package. Under the existing ROS Humble and message overlays,
`validation.test_rc_control` and `validation.test_rc_input` passed 10/10 with
no skips. The local combined check of RC, trajectory, global-reference and
joint-trajectory behavior passed 38/38 with the two pre-existing ROS graph
tests skipped by their declared environment guard.

This evidence covers the `CommandProcessor.set_rc_desired` boundary only. The
node/native integration and all physical RC cases remain unverified and are not
represented as a pass.
