"""Pure, deterministic evaluator for an explicitly supplied EGO uniform B-spline.

This is an OFFLINE evaluation seam for the #102 prerequisite: it reproduces, in pure
Python with no ROS/planner/SITL dependency, the exact uniform B-spline mathematics of
the reviewed upstream source (Modules/ego_planner_swarm/bspline_opt/src/uniform_bspline.cpp,
pinned upstream 5dcd8cfa764d):

- Initial knot layout (setUniformBspline): with order p and N control points, n = N-1,
  m = n + p + 1; u(i) = (i - p) * interval for i <= p, else u(i) = u(i-1) + interval.
- Valid domain (getTimeSpan): u in [u(p), u(m-p)].
- de Boor (evaluateDeBoor): clamp u to [u(p), u(m-p)], find the knot span, then the
  standard p-level corner-cutting recursion.
- evaluateDeBoorT: evaluate at t + u(p), so curve time t in [0, duration] with
  duration = u(m-p) - u(p) (getTimeSum).
- getDerivative: control points Q_i = p * (P_{i+1} - P_i) / (u(i+p+1) - u(i+1)) computed
  with the CURRENT knots, order p-1, and the derivative's knot vector is the parent's
  knots with the FIRST and LAST cut (u_.segment(1, rows-2)) -- it is NOT re-derived as a
  fresh uniform layout. Evaluated with the SAME absolute shift t + u(p).

Real EGO output is NOT always the initial uniform layout: upstream lengthenTime(ratio)
(planner_manager.cpp:642) mutates the interior knots in place, and traj_server
(traj_server_for_prometheus.cpp bsplineCallback) does `setKnot(msg->knots)`, replacing the
uniform vector wholesale. Accepting only the initial uniform layout would therefore reject
genuine planner trajectories. So a supplied knot vector is honoured when it is:

  * exactly m+1 = n+p+2 long (matches the control-point count and order),
  * all finite (non-bool), and
  * STRICTLY increasing (no repeats, non-monotonic, or degenerate spans -- the upstream
    loop would otherwise divide by zero or mis-span).

Anything else fails closed. No physics, force, occupancy or ROS work happens here.

Yaw is deliberately NOT evaluated here. Upstream traj_server (traj_server_for_prometheus.cpp)
only ever setKnot()s the POSITION spline and derives yaw from position / last_yaw / wall clock
in calculate_yaw(); it never evaluates a yaw_pts curve (and its publisher does not fill yaw_pts).
Reproducing that needs a live wall clock, which this offline seam does not have. So this module
exposes position (and its velocity/acceleration derivatives) only; the adapter requires an
explicit finite fallback yaw instead.
"""
import math
from numbers import Real

DEFAULT_INTERVAL_S = 0.1          # traj_server_for_prometheus.cpp constructs with 0.1
DEFAULT_ORDER = 3                 # ego_replan_fsm publishes a cubic (order 3) Bspline
EGO_ORDER = 3                     # the only order real EGO output uses; enforced fail-closed
MAX_POINTS = 4096                 # generous structural cap; malformed payloads fail closed


class SplineError(ValueError):
    """A malformed or out-of-domain B-spline payload; always fail closed."""


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise SplineError(f"{name} must be a finite real number")
    return float(value)


def _uniform_knots(order, num_points, interval):
    """Reproduce the upstream setUniformBspline knot vector exactly."""
    n = num_points - 1
    m = n + order + 1
    knots = [0.0] * (m + 1)
    for i in range(m + 1):
        if i <= order:
            knots[i] = float(-order + i) * interval
        else:
            knots[i] = knots[i - 1] + interval
    return knots


def _validate_knots(knots, order, num_points):
    """Accept an explicit knot vector (real EGO output) or fail closed.

    Must be exactly num_points + order + 1 (= m+1) finite, strictly increasing numbers.
    Strict increase is required: a repeat or non-monotonic knot would make the de Boor /
    derivative denominator zero (division by zero) or produce a degenerate span.
    """
    if isinstance(knots, (str, bytes)):
        raise SplineError("knots must be a sequence of finite numbers")
    try:
        given = tuple(_finite(v, "knot") for v in knots)
    except TypeError as error:
        raise SplineError("knots must be a sequence of finite numbers") from error
    expected = num_points + order + 1
    if len(given) != expected:
        raise SplineError(f"knot count must be {expected} (= control points + order + 1)")
    for i in range(1, len(given)):
        if not given[i] > given[i - 1]:
            raise SplineError("knots must be strictly increasing")
    return list(given)


class UniformBspline:
    """One uniform B-spline of scalar or vector control points (de Boor).

    If ``knots`` is supplied it is validated (exact length, finite, strictly increasing)
    and used as-is for evaluation and derivatives, mirroring upstream setKnot. Otherwise the
    upstream uniform layout is derived from ``interval``.
    """

    def __init__(self, order, control_points, interval=DEFAULT_INTERVAL_S, knots=None):
        if isinstance(order, bool) or type(order) is not int or order < 1:
            raise SplineError("order must be a positive integer")
        if isinstance(control_points, (str, bytes)):
            raise SplineError("control_points must be a sequence of numbers or 3-vectors")
        try:
            points = list(control_points)
        except TypeError as error:
            raise SplineError("control_points must be a sequence") from error
        if not points or len(points) > MAX_POINTS:
            raise SplineError("control_points must be a non-empty bounded sequence")
        interval = _finite(interval, "interval")
        if interval <= 0:
            raise SplineError("interval must be positive")

        # A control point is either a scalar (yaw) or a 3-vector (position ENU).
        first = points[0]
        if isinstance(first, (str, bytes)):
            raise SplineError("control point must be a number or 3-vector")
        if isinstance(first, Real) and not isinstance(first, bool):
            dimension = 1
            coerced = [(_finite(p, "control_point"),) for p in points]
        else:
            dimension = 3
            coerced = []
            for p in points:
                if isinstance(p, (str, bytes)):
                    raise SplineError("control point must be a 3-vector")
                try:
                    vec = tuple(p)
                except TypeError as error:
                    raise SplineError("control point must be a 3-vector") from error
                if len(vec) != 3:
                    raise SplineError("position control point must have three components")
                coerced.append(tuple(_finite(c, "control_point") for c in vec))
        # Reject mixed scalar/vector payloads.
        if any(len(p) != dimension for p in coerced):
            raise SplineError("control points must not mix scalars and vectors")
        # Need at least order+1 control points for a non-degenerate curve.
        if len(coerced) < order + 1:
            raise SplineError("control point count must be at least order + 1")

        self.order = order
        self.interval = interval
        self.dimension = dimension
        self._points = coerced
        self._n = len(coerced) - 1
        self._m = self._n + order + 1
        if knots is None:
            self._knots = _uniform_knots(order, len(coerced), interval)
        else:
            self._knots = _validate_knots(knots, order, len(coerced))

    @property
    def knots(self):
        return tuple(self._knots)

    @property
    def num_control_points(self):
        return len(self._points)

    def time_span(self):
        """(u_min, u_max) = (u(p), u(m-p)); the absolute curve domain."""
        return self._knots[self.order], self._knots[self._m - self.order]

    @property
    def duration(self):
        lo, hi = self.time_span()
        return hi - lo

    def _clamp(self, u):
        lo, hi = self.time_span()
        return min(max(lo, u), hi)

    def evaluate(self, u):
        """de Boor at absolute knot coordinate u (clamped into the valid domain)."""
        u = _finite(u, "u")
        ub = self._clamp(u)
        p = self.order
        knots = self._knots
        # Find the knot span [u(k), u(k+1]] containing ub.
        k = p
        while not (knots[k + 1] >= ub):
            k += 1
        d = [self._points[k - p + i] for i in range(p + 1)]
        for r in range(1, p + 1):
            for i in range(p, r - 1, -1):
                denom = knots[i + 1 + k - r] - knots[i + k - p]
                if denom == 0.0:
                    raise SplineError("degenerate knot interval (division by zero)")
                alpha = (ub - knots[i + k - p]) / denom
                prev, cur = d[i - 1], d[i]
                d[i] = tuple((1.0 - alpha) * prev[c] + alpha * cur[c] for c in range(self.dimension))
        result = d[p]
        return result[0] if self.dimension == 1 else result

    def evaluate_t(self, t):
        """Curve-time evaluation: t in [0, duration], shifted by u(p)."""
        t = _finite(t, "t")
        u_min = self._knots[self.order]
        return self.evaluate(t + u_min)

    def derivative(self):
        """The derivative B-spline (order p-1), reproducing upstream getDerivative.

        Control points use the CURRENT knots; the derivative's knot vector is the parent's
        with the first and last knot cut (u_.segment(1, rows-2)) -- never re-derived.
        """
        p = self.order
        if p < 1:
            raise SplineError("cannot differentiate a zero-order spline")
        knots = self._knots
        points = self._points
        derived = []
        for i in range(len(points) - 1):
            denom = knots[i + p + 1] - knots[i + 1]
            if denom == 0.0:
                raise SplineError("degenerate knot interval in derivative")
            derived.append(tuple(
                p * (points[i + 1][c] - points[i][c]) / denom for c in range(self.dimension)))
        out = object.__new__(UniformBspline)
        out.order = p - 1
        out.interval = self.interval
        out.dimension = self.dimension
        out._points = derived
        out._n = len(derived) - 1
        out._m = out._n + out.order + 1
        out._knots = list(knots[1:-1])          # cut the first and last knot (upstream)
        if len(out._knots) != out._m + 1:
            raise SplineError("derivative knot layout is inconsistent")
        return out


class EgoSpline:
    """An EGO Bspline position payload (order 3, ENU map frame).

    Mirrors the traj_utils/Bspline.msg position fields supplied explicitly by the caller;
    nothing is read from ROS. The position control points are ENU/metre map-frame vectors.
    The supplied ``knots`` (when given) are honoured exactly as upstream setKnot does, so
    lengthened/non-uniform real planner output evaluates correctly.

    Only the real EGO order (3) is accepted: a lower order would defer a failure to the
    adapter's acceleration (second-derivative) evaluation, so it is rejected up front. Yaw
    is intentionally absent (see module docstring): this seam exposes position, velocity
    and acceleration only; the adapter requires an explicit finite fallback yaw.
    """

    def __init__(self, order, knots, pos_pts, interval=DEFAULT_INTERVAL_S):
        if order != EGO_ORDER:
            raise SplineError(f"only the EGO order ({EGO_ORDER}) is supported offline")
        position = UniformBspline(order, pos_pts, interval, knots=knots)
        # An EGO position payload is always 3-vector (ENU x,y,z). A scalar control-point
        # sequence must fail closed at CONSTRUCTION, not later at the adapter's step.
        if position.dimension != 3:
            raise SplineError("position control points must be 3-vectors (ENU x,y,z)")
        self.position = position
        self.order = position.order
        self.interval = position.interval
        self.duration = position.duration
        self.start_time_s = position.time_span()[0]

    def position_at(self, t):
        """ENU position (x, y, z) at curve time t (clamped to [0, duration])."""
        return self.position.evaluate_t(t)

    def velocity_at(self, t):
        return self.position.derivative().evaluate_t(t)

    def acceleration_at(self, t):
        return self.position.derivative().derivative().evaluate_t(t)
