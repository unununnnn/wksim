"""CANDIDATE-ONLY exact geometric clearance certificate for a cubic EGO B-spline.

Status: **candidate, not wired, not default.**  Nothing in the committed runtime
imports this module; ``Simulator/wksim_planning/ego_scene_admission.py`` and
``Simulator/wksim_runtime/planner_transport_pump.py`` are unchanged and keep
deciding admission.  Promoting this predicate to the default is an explicit owner
decision (see ``docs/plan/102-exact-clearance-candidate.md``).

Why it exists
-------------

The committed strict gate certifies, per knot interval, the *axis-aligned
bounding box* of the active control-point window against the obstacle AABB.  The
independent audit ``validation/coordination/deepseek-g3-strict-gate-20260914-01/``
measured the consequence: the verdict is a function of the control-point
representation, not of the geometric curve.  One exactly identical curve
(maximum deviation 2.2e-15 m) is REJECTED at 9 and 13 control points and ADMITTED
from 23 control points up; the committed recorded planner payload is admitted
with a certified net clearance of 0.37725020658857944 m while its true clearance
is 0.9971917383329542 m; and no positive ``required_clearance`` can admit the
9/13-control witnesses (they would need a negative threshold).

What this module certifies
--------------------------

For every active knot interval ``[u_j, u_{j+1}]`` of the exact evaluation domain
``[u_p, u_{m-p}]`` it produces a **certified bracket**

    obstacle_lower_j <= min_{t in [u_j,u_{j+1}]} dist(gamma(t), obstacle) <= obstacle_upper_j

and the same for the map-boundary clearance

    inset_lower_j    <= min_{t in [u_j,u_{j+1}]} g(gamma(t))          <= inset_upper_j

where ``dist(., obstacle)`` is the exact Euclidean point-to-AABB distance and
``g(x) = min_i min(x_i - low_i, high_i - x_i)`` is the smallest signed distance
to any map face (negative outside the map).  ``gamma`` is the *continuous* cubic
curve, not a sampled polyline: no chord, segment or time grid is involved.

Soundness argument (Lipschitz subdivision, no sampling assumption)
-----------------------------------------------------------------

1. On a knot interval ``[a, b]`` the curve has a certified speed bound ``V``:
   ``||gamma'(t)|| <= V`` for every ``t in [a, b]``.  ``V`` comes from the
   B-spline derivative identity ``Q_i = p (P_{i+1} - P_i) / (U_{i+p+1} - U_{i+1})``
   with the parent knots cut by one (``U[1:-1]``): the derivative is a spline of
   degree ``p-1``, so on any span it is a convex combination of its active
   control points and its norm is bounded by the largest active ``||Q_i||``.  A
   superset of the active derivative window is used, which can only loosen the
   bound, never invalidate it.
2. Both target functions are 1-Lipschitz: ``dist(., B)`` with respect to the
   Euclidean norm and ``g`` with respect to the L-infinity norm (hence also with
   respect to the Euclidean norm).  So for any sub-interval ``[c, d]`` with
   midpoint ``m`` and the exact value ``f(m)``,

       min_{t in [c,d]} f(t) >= f(m) - V (d - c) / 2      (certified lower bound)
       min_{t in [c,d]} f(t) <= f(m)                       (valid upper bound)

   Each midpoint value ``f(m)`` is an *exact evaluation* of the curve at a single
   **absolute knot coordinate** ``u`` (``position.evaluate(u)``, not curve-time
   ``position_at``).  The constructed float ``u`` may differ from the exact
   midpoint by at most ``ulp(u)/2``.  That parameter displacement is charged as
   ``V * ulp(u)/2`` and is required to stay inside the declared
   ``FLOAT_GUARD_M`` envelope.  Fail-closed **before** ``evaluate()``, with
   ``evaluations=0``, empty ``spans`` and ``bounds_scope=None``:

   1. any active span whose required interior midpoint is not a representable
      strict-interior float -- ``rejected`` /
      ``certificate_structure_invalid``;
   2. else any span whose speed-scaled ULP exceeds ``FLOAT_GUARD_M`` --
      ``indeterminate`` / ``parameter_roundoff_exceeds_envelope``;
   3. else any span whose requested n-partition is unrepresentable, outside
      the open interval, or non-unique -- ``rejected`` /
      ``certificate_structure_invalid``.

   (1) beats (2) beats (3).  A ``SpanBracket`` is emitted only after a valid
   interior sample exists; unrepresentable partitions never fabricate per-span
   bounds.  Ordinary knot translations that stay inside the envelope
   (``+1`` / ``+4`` seconds on map-scale EGO knots) keep the same verdict;
   arbitrary translation invariance is not claimed.
   A uniform partition with ``n = ceil(V (b-a) / (2 (t - 2 eps)))`` sub-intervals
   therefore yields a span bracket of width ``V (b-a) / n + 2 eps`` <= ``t``
   when the envelope holds, where ``eps`` is the declared absolute float guard.
3. The global minimum over the whole curve is the minimum of the per-span minima,
   so the reported global bracket is the min of the span lower bounds and the min
   of the span upper bounds.  Because the span attaining the smallest lower bound
   also bounds the global upper bound, the global bracket is no wider than the
   span bracket that produced it.

Decision semantics (fail closed, declared band)
-----------------------------------------------

``tolerance_m`` (default ``1e-3`` m) is the declared resolution.  Writing
``required`` for the committed ``required_clearance`` and ``radius`` for the
committed ``vehicle_radius`` (both clearances below are already net of
``radius``):

* ``ADMITTED`` -- every span closed (bracket width <= tolerance) and every span's
  *lower* bound is ``>= required``.  Sound: the true clearance is above it.
* ``REJECTED`` -- some span's *upper* bound is ``< required``: the true clearance
  is provably too small.  Also used, fail-closed, for a structurally unusable
  spline (``reason = certificate_structure_invalid`` / ``non_monotone_knots`` /
  ``degenerate_domain`` / ``no_active_interval``), including finite inputs whose
  derivative norms, products, node counts, slack, evaluations or distances
  overflow to a non-finite value, and spans whose requested midpoint or interior
  partition is not a representable interior float.
* ``INDETERMINATE`` -- the proof could not be closed, either because the true
  minimum lies inside the declared band ``(required - t, required + t)``
  (``clearance_within_tolerance_band``), because a work cap was reached
  (``work_cap_exhausted``), or because a span's speed-scaled parameter ULP
  exceeds the declared ``FLOAT_GUARD_M`` envelope
  (``parameter_roundoff_exceeds_envelope``).  ``admitted`` is False in all
  three cases.

Consequently the decision is a function of the geometric curve outside the band:
a curve whose true clearance is ``>= required + t`` is admitted in *every*
representation (closing the bracket only needs the width, not the density), and
one below ``required - t`` is rejected in every representation.

What this module does NOT do
----------------------------

It does not sample the curve and call the result certified; it does not use a
segment/chord distance anywhere; it does not read a wall clock, mint an
identifier, open a socket, or touch ROS/DDS/UE/SITL/FC/MATLAB/native code; it does
not import or modify the committed admission gate, the transport pump, the
adapter or the session; and it makes no dynamics, tracking-error, controller-lag,
force, impulse, terrain, planner, flight-safety or #102/#39/#29/#33 acceptance
claim.  The obstacle is assumed to be exactly the committed vertical AABB for the
whole trajectory duration and the vehicle extent behind ``vehicle_radius`` is
assumed spherical.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Optional, Tuple

from Simulator.wksim_planning.ego_evaluator import EGO_ORDER, EgoSpline
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    PlannerSceneBinding,
)

EVIDENCE_KIND = "lipschitz_bracket_certified"
CANDIDATE_STATUS = "candidate_only"

# Declared resolution of the certified bracket.  The audit's R1 band is 2*t.
DEFAULT_TOLERANCE_M = 1e-3
MAX_TOLERANCE_M = 0.1
# Absolute float guard added to every certified bracket corner (metres), and
# the declared parameter-roundoff envelope.  A representable span whose
# speed-scaled ULP ``0.5 * V * ulp(|u|)`` exceeds this value is fail-closed
# before sampling (indeterminate).  An unrepresentable midpoint or n-partition
# is fail-closed before sampling (rejected, empty spans).
FLOAT_GUARD_M = 1e-9

# Explicit work caps (both are hard: hitting one yields INDETERMINATE unless a
# conclusive rejection was already found).
DEFAULT_MAX_NODES_PER_SPAN = 1 << 16           # 65536 sub-intervals per span
DEFAULT_MAX_EVALUATIONS = 1 << 21              # 2097152 curve evaluations

STATUS_ADMITTED = "admitted"
STATUS_REJECTED = "rejected"
STATUS_INDETERMINATE = "indeterminate"

REASON_STRUCTURE = "certificate_structure_invalid"
REASON_KNOTS = "non_monotone_knots"
REASON_DOMAIN = "degenerate_domain"
REASON_NO_INTERVAL = "no_active_interval"
REASON_WORK_CAP = "work_cap_exhausted"
REASON_BAND = "clearance_within_tolerance_band"
REASON_ROUNDOFF = "parameter_roundoff_exceeds_envelope"
REASON_OBSTACLE = "obstacle_clearance_below_required"
REASON_MAP = "map_inset_below_margin"

CERTIFICATE_REASONS = (
    REASON_STRUCTURE,
    REASON_KNOTS,
    REASON_DOMAIN,
    REASON_NO_INTERVAL,
    REASON_WORK_CAP,
    REASON_BAND,
    REASON_ROUNDOFF,
    REASON_OBSTACLE,
    REASON_MAP,
)

BINDING_OBJECT_OBSTACLE = "obstacle"
BINDING_OBJECT_MAP_INSET = "map_inset"
BOUNDS_SCOPE_CURVE = "continuous_curve"
BOUNDS_SCOPE_PARTIAL = "partial_evaluated_spans"

NON_CLAIMS = (
    "candidate only: this module is not wired into the committed admission gate, "
    "the transport pump, the adapter or the session, and it is not the default "
    "predicate; promotion is an explicit owner decision",
    "no dynamics, tracking-error, controller-lag, force, impulse, sensor, "
    "planner, socket, UE, SITL, ROS/DDS, flight-controller, native-build or "
    "flight-safety claim",
    "the obstacle is exactly the committed vertical AABB for the whole "
    "trajectory duration; Terrain15D / terrain height is never read",
    "the vehicle extent behind vehicle_radius is assumed spherical",
    "no identifier is minted and no wall clock is read",
    "the reported bounds are certified brackets at the declared tolerance, not "
    "an exact-real proof; the gap between them is the declared resolution",
    "ordinary knot translations that stay inside the FLOAT_GUARD_M parameter-"
    "roundoff envelope keep the same verdict; arbitrary translation invariance "
    "outside that envelope is not claimed",
)


class ExactClearanceError(ValueError):
    """Caller/protocol error raised before any certificate is produced.

    Structural problems *inside* a supplied spline are NOT raised: they are
    returned as a fail-closed certificate with ``status == "rejected"`` and a
    structural ``reason``, mirroring the committed gate's fail-closed pattern.
    """

    def __init__(self, reason: str, message: str = ""):
        if reason not in CERTIFICATE_REASONS:
            raise ValueError("unknown exact clearance reason: %r" % (reason,))
        super().__init__("[%s] %s" % (reason, message) if message else reason)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class SpanBracket:
    """Certified bracket of one active knot interval (centreline metres).

    Emitted only after every requested interior sample of the span is a
    representable strict-interior float.  Unrepresentable midpoints or
    collapsed partitions produce no ``SpanBracket`` (empty ``spans``).
    """

    span_index: int
    u_start: float
    u_end: float
    obstacle_lower: float
    obstacle_upper: float
    inset_lower: float
    inset_upper: float
    speed_bound: float
    nodes: int
    evaluations: int
    closed: bool
    conclusive: bool


@dataclass(frozen=True)
class ExactClearanceCertificate:
    """Structured, machine-readable evidence of one candidate assessment.

    ``obstacle_*`` and ``map_inset_*`` clearances are NET of ``vehicle_radius``
    (the committed margin convention), so the committed ``required_clearance`` is
    the single threshold for both.  When ``bounds_scope == "continuous_curve"``,
    ``*_lower``/``*_upper`` are certified bounds on the minimum over the whole
    continuous curve.  They are ``None`` when the certificate could not be built,
    or when only a prefix of the spans was evaluated (``bounds_scope ==
    "partial_evaluated_spans"``); per-span evidence stays in ``spans``.
    """

    candidate_only: bool
    status: str
    admitted: bool
    evidence_kind: str
    reason: Optional[str]
    tolerance_m: float
    float_guard_m: float
    tolerance_met: bool
    obstacle_clearance_lower: Optional[float]
    obstacle_clearance_upper: Optional[float]
    map_inset_clearance_lower: Optional[float]
    map_inset_clearance_upper: Optional[float]
    binding_object: Optional[str]
    binding_span_index: Optional[int]
    binding_u_start: Optional[float]
    binding_u_end: Optional[float]
    max_speed_bound_m_per_s: Optional[float]
    vehicle_radius: float
    required_clearance: float
    clearance_margin: float
    scene_id: str
    scene_hash: str
    geometry_id: str
    profile_hash: str
    span_count: int
    evaluated_span_count: int
    nodes: int
    evaluations: int
    max_nodes_per_span: int
    max_evaluations: int
    spans: Tuple[SpanBracket, ...]
    bounds_scope: Optional[str] = None
    non_claims: Tuple[str, ...] = NON_CLAIMS

    def to_dict(self) -> dict:
        """JSON-serializable view (used by the receipt and the tests)."""
        return {
            "candidate_only": self.candidate_only,
            "status": self.status,
            "admitted": self.admitted,
            "evidence_kind": self.evidence_kind,
            "reason": self.reason,
            "tolerance_m": self.tolerance_m,
            "float_guard_m": self.float_guard_m,
            "tolerance_met": self.tolerance_met,
            "obstacle_clearance_lower": self.obstacle_clearance_lower,
            "obstacle_clearance_upper": self.obstacle_clearance_upper,
            "map_inset_clearance_lower": self.map_inset_clearance_lower,
            "map_inset_clearance_upper": self.map_inset_clearance_upper,
            "binding_object": self.binding_object,
            "binding_span_index": self.binding_span_index,
            "binding_u_start": self.binding_u_start,
            "binding_u_end": self.binding_u_end,
            "max_speed_bound_m_per_s": self.max_speed_bound_m_per_s,
            "vehicle_radius": self.vehicle_radius,
            "required_clearance": self.required_clearance,
            "clearance_margin": self.clearance_margin,
            "scene_id": self.scene_id,
            "scene_hash": self.scene_hash,
            "geometry_id": self.geometry_id,
            "profile_hash": self.profile_hash,
            "span_count": self.span_count,
            "evaluated_span_count": self.evaluated_span_count,
            "nodes": self.nodes,
            "evaluations": self.evaluations,
            "max_nodes_per_span": self.max_nodes_per_span,
            "max_evaluations": self.max_evaluations,
            "bounds_scope": self.bounds_scope,
            "spans": [
                {
                    "span_index": span.span_index,
                    "u_start": span.u_start,
                    "u_end": span.u_end,
                    "obstacle_lower": span.obstacle_lower,
                    "obstacle_upper": span.obstacle_upper,
                    "inset_lower": span.inset_lower,
                    "inset_upper": span.inset_upper,
                    "speed_bound": span.speed_bound,
                    "nodes": span.nodes,
                    "evaluations": span.evaluations,
                    "closed": span.closed,
                    "conclusive": span.conclusive,
                }
                for span in self.spans
            ],
            "non_claims": list(self.non_claims),
        }


# --------------------------------------------------------------------------
# exact geometric primitives (no sampling anywhere)
# --------------------------------------------------------------------------
def point_box_distance(point: Any, box_min: Any, box_max: Any) -> float:
    """Exact Euclidean distance from a point to a closed axis-aligned box."""
    total = 0.0
    for coordinate, low, high in zip(point, box_min, box_max):
        if coordinate < low:
            delta = low - coordinate
        elif coordinate > high:
            delta = coordinate - high
        else:
            continue
        total += delta * delta
    return math.sqrt(total)


def _is_finite_real(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _finite_point(point: Any) -> bool:
    try:
        coordinates = tuple(point)
    except TypeError:
        return False
    return len(coordinates) == 3 and all(_is_finite_real(value) for value in coordinates)


def _parameter_ulp(u_start: float, u_end: float) -> float:
    scale = max(abs(u_start), abs(u_end))
    return math.ulp(scale) if scale != 0.0 else math.ulp(0.0)


def _span_midpoint_representable(u_start: float, u_end: float) -> bool:
    width = u_end - u_start
    if not (width > 0.0 and math.isfinite(width)):
        return False
    mid = u_start + 0.5 * width
    return bool(u_start < mid < u_end)


def _interior_partition(u_start: float, u_end: float, nodes: int):
    """Return unique strict-interior midpoints, or ``None`` if unrepresentable."""
    if nodes < 1:
        return None
    width = u_end - u_start
    if not (width > 0.0 and math.isfinite(width)):
        return None
    step = width / nodes
    if not math.isfinite(step):
        return None
    samples = []
    for node in range(nodes):
        u = u_start + (node + 0.5) * step
        if not (math.isfinite(u) and u_start < u < u_end):
            return None
        samples.append(u)
    if len(set(samples)) != nodes:
        return None
    return samples


def _parameter_roundoff_m(speed: float, u_start: float, u_end: float) -> float:
    return 0.5 * speed * _parameter_ulp(u_start, u_end)


def inward_face_clearance(point: Any, bounds_min: Any, bounds_max: Any) -> float:
    """Smallest signed distance from a point to any map face (negative outside).

    ``min_i min(p_i - low_i, high_i - p_i)``.  The function is 1-Lipschitz in the
    L-infinity norm, hence also in the Euclidean norm.
    """
    return min(
        min(coordinate - low, high - coordinate)
        for coordinate, low, high in zip(point, bounds_min, bounds_max)
    )


# --------------------------------------------------------------------------
# structure reading and validation
# --------------------------------------------------------------------------
def _read_structure(spline: EgoSpline):
    """Return (order, knots, control_points) or raise _StructureFailure."""
    try:
        position = spline.position
        order = position.order
        knots = tuple(position.knots)
        points = tuple(position._points)
    except (AttributeError, TypeError) as error:
        raise _StructureFailure(REASON_STRUCTURE, "spline structure is unreadable") from error
    if isinstance(order, bool) or type(order) is not int or order < 1:
        raise _StructureFailure(REASON_STRUCTURE, "order must be a positive integer")
    if order != EGO_ORDER:
        raise _StructureFailure(REASON_STRUCTURE, "only the EGO cubic order is certifiable offline")
    if len(points) < order + 1:
        raise _StructureFailure(REASON_STRUCTURE, "control point count must be at least order + 1")
    if len(knots) != len(points) + order + 1:
        raise _StructureFailure(REASON_STRUCTURE, "knot cardinality must be control points + order + 1")
    for value in knots:
        if not _is_finite_real(value):
            raise _StructureFailure(REASON_STRUCTURE, "knots must be finite real numbers")
    for index in range(1, len(knots)):
        if not knots[index] > knots[index - 1]:
            raise _StructureFailure(REASON_KNOTS, "knots must be strictly increasing")
    for point in points:
        if isinstance(point, (str, bytes)):
            raise _StructureFailure(REASON_STRUCTURE, "control points must be three-vectors")
        try:
            coordinates = tuple(point)
        except TypeError as error:
            raise _StructureFailure(REASON_STRUCTURE, "control points must be three-vectors") from error
        if len(coordinates) != 3:
            raise _StructureFailure(REASON_STRUCTURE, "control points must be three-vectors")
        for coordinate in coordinates:
            if not _is_finite_real(coordinate):
                raise _StructureFailure(REASON_STRUCTURE, "control points must be finite real numbers")
    start_u = knots[order]
    end_u = knots[len(points)]
    if not end_u > start_u:
        raise _StructureFailure(REASON_DOMAIN, "the exact evaluation domain must be non-degenerate")
    return order, knots, points


class _StructureFailure(Exception):
    def __init__(self, reason: str, message: str = ""):
        super().__init__("%s: %s" % (reason, message) if message else reason)
        self.reason = reason
        self.message = message


def derivative_speed_bounds(order: int, knots: Tuple[float, ...],
                            points: Tuple[Tuple[float, float, float], ...]) -> Tuple[float, ...]:
    """Per active knot span certified upper bound on ||gamma'(t)||.

    ``Q_i = p (P_{i+1} - P_i) / (U_{i+p+1} - U_{i+1})`` are the derivative spline's
    control points (the derivative's knot vector is the parent's cut by one, the
    identity the repo's evaluator also uses).  On a span the degree-(p-1)
    derivative is a convex combination of its active control points; this returns
    the largest norm over a *superset* of that active window, which is a valid
    bound.  A degenerate denominator is impossible here (strictly increasing
    knots were validated) but is guarded anyway.
    """
    count = len(points) - 1
    derivative_points = []
    for index in range(count):
        denominator = knots[index + order + 1] - knots[index + 1]
        if not denominator > 0.0:
            raise _StructureFailure(REASON_KNOTS, "degenerate knot interval in the derivative")
        components = tuple(
            order * (points[index + 1][axis] - points[index][axis]) / denominator
            for axis in range(3))
        if any(not math.isfinite(value) for value in components):
            raise _StructureFailure(
                REASON_STRUCTURE, "non-finite derivative control point")
        derivative_points.append(components)
    norms = []
    for point in derivative_points:
        norm = math.sqrt(sum(value * value for value in point))
        if not math.isfinite(norm):
            raise _StructureFailure(REASON_STRUCTURE, "non-finite derivative speed bound")
        norms.append(norm)
    global_bound = max(norms)
    bounds = []
    for span in range(order, len(points)):
        first = max(0, span - order - 1)
        last = min(span, len(derivative_points) - 1)
        if first > last:
            bounds.append(global_bound)
            continue
        bounds.append(max(norms[index] for index in range(first, last + 1)))
    return tuple(bounds)


# --------------------------------------------------------------------------
# the certificate
# --------------------------------------------------------------------------
@dataclass
class _Budget:
    max_evaluations: int
    used_evaluations: int = 0

    def request(self, wanted: int, per_span_cap: int) -> Tuple[int, bool]:
        """Return (granted_nodes, truncated)."""
        granted = min(wanted, per_span_cap)
        truncated = granted < wanted
        remaining = self.max_evaluations - self.used_evaluations
        if granted > remaining:
            granted = max(0, remaining)
            truncated = True
        self.used_evaluations += granted
        return granted, truncated


def certify_exact_clearance(
        spline: EgoSpline, *,
        binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
        tolerance_m: float = DEFAULT_TOLERANCE_M,
        max_nodes_per_span: int = DEFAULT_MAX_NODES_PER_SPAN,
        max_evaluations: int = DEFAULT_MAX_EVALUATIONS,
) -> ExactClearanceCertificate:
    """Certify the continuous cubic curve's clearance against the committed scene.

    Pure, deterministic, fail-closed.  Returns an ``ExactClearanceCertificate``;
    raises ``ExactClearanceError`` only for caller/protocol errors (wrong types,
    out-of-range tolerance, invalid caps), never for a geometric shortfall or an
    unusable spline structure -- those come back as a rejected/indeterminate
    certificate so a caller cannot mistake an exception path for an admission.
    """
    if not isinstance(spline, EgoSpline):
        raise ExactClearanceError(REASON_STRUCTURE, "spline must be an EgoSpline")
    if not isinstance(binding, PlannerSceneBinding):
        raise ExactClearanceError(REASON_STRUCTURE, "binding must be a PlannerSceneBinding")
    if (isinstance(tolerance_m, bool) or not isinstance(tolerance_m, Real)
            or not math.isfinite(tolerance_m) or tolerance_m <= 0.0):
        raise ExactClearanceError(
            REASON_STRUCTURE, "tolerance_m must be a positive finite number of metres")
    if tolerance_m > MAX_TOLERANCE_M:
        raise ExactClearanceError(
            REASON_STRUCTURE,
            "tolerance_m must not exceed the declared maximum %r m" % (MAX_TOLERANCE_M,))
    if tolerance_m <= 4.0 * FLOAT_GUARD_M:
        raise ExactClearanceError(
            REASON_STRUCTURE,
            "tolerance_m must exceed the declared float guard (%r m)" % (4.0 * FLOAT_GUARD_M,))
    if isinstance(max_nodes_per_span, bool) or type(max_nodes_per_span) is not int or max_nodes_per_span < 1:
        raise ExactClearanceError(REASON_STRUCTURE, "max_nodes_per_span must be a positive integer")
    if isinstance(max_evaluations, bool) or type(max_evaluations) is not int or max_evaluations < 1:
        raise ExactClearanceError(REASON_STRUCTURE, "max_evaluations must be a positive integer")

    profile = binding.profile
    radius = float(profile.vehicle_radius)
    required = float(profile.required_clearance)
    margin = radius + required
    tolerance = float(tolerance_m)
    obstacle_low = profile.obstacle.minimum
    obstacle_high = profile.obstacle.maximum
    map_low = profile.map_bounds.minimum
    map_high = profile.map_bounds.maximum

    def base(reason: Optional[str], status: str, **overrides) -> ExactClearanceCertificate:
        values = dict(
            candidate_only=True,
            status=status,
            admitted=False,
            evidence_kind=EVIDENCE_KIND,
            reason=reason,
            tolerance_m=tolerance,
            float_guard_m=FLOAT_GUARD_M,
            tolerance_met=False,
            obstacle_clearance_lower=None,
            obstacle_clearance_upper=None,
            map_inset_clearance_lower=None,
            map_inset_clearance_upper=None,
            binding_object=None,
            binding_span_index=None,
            binding_u_start=None,
            binding_u_end=None,
            max_speed_bound_m_per_s=None,
            vehicle_radius=radius,
            required_clearance=required,
            clearance_margin=margin,
            scene_id=binding.scene_id,
            scene_hash=binding.scene_hash,
            geometry_id=binding.geometry_id,
            profile_hash=profile.profile_hash,
            span_count=0,
            evaluated_span_count=0,
            nodes=0,
            evaluations=0,
            max_nodes_per_span=int(max_nodes_per_span),
            max_evaluations=int(max_evaluations),
            spans=(),
        )
        values.update(overrides)
        return ExactClearanceCertificate(**values)

    try:
        order, knots, points = _read_structure(spline)
        speed_bounds = derivative_speed_bounds(order, knots, points)
    except _StructureFailure as failure:
        return base(failure.reason, STATUS_REJECTED)
    except OverflowError:
        return base(REASON_STRUCTURE, STATUS_REJECTED)

    first_span = order
    last_span = len(points) - 1                 # last certified span index (m - p - 1 = n)
    span_indices = list(range(first_span, last_span + 1))
    if not span_indices:
        return base(REASON_NO_INTERVAL, STATUS_REJECTED)

    budget = _Budget(max_evaluations=int(max_evaluations))
    # The bracket half-width of a sub-interval is V*step/2, and the guard is added
    # to both corners, so the target half-width is tolerance - 2*guard.
    target_half_width = tolerance - 2.0 * FLOAT_GUARD_M
    spans = []
    obstacle_lower = math.inf
    obstacle_upper = math.inf
    inset_lower = math.inf
    inset_upper = math.inf
    binding_object = None
    binding_span = None
    conclusive_reason = None
    unresolved_reason = None
    unresolved_span = None
    tolerance_met = True
    peak_speed = 0.0

    def snapshot():
        complete = bool(spans) and len(spans) == len(span_indices)
        return dict(
            tolerance_met=tolerance_met,
            obstacle_clearance_lower=None if not complete else obstacle_lower - radius,
            obstacle_clearance_upper=None if not complete else obstacle_upper - radius,
            map_inset_clearance_lower=None if not complete else inset_lower - radius,
            map_inset_clearance_upper=None if not complete else inset_upper - radius,
            max_speed_bound_m_per_s=peak_speed if spans else None,
            span_count=len(span_indices),
            evaluated_span_count=len(spans),
            nodes=budget.used_evaluations,
            evaluations=budget.used_evaluations,
            spans=tuple(spans),
            bounds_scope=BOUNDS_SCOPE_CURVE if complete else (
                BOUNDS_SCOPE_PARTIAL if spans else None),
        )

    def reject_nonfinite():
        return base(REASON_STRUCTURE, STATUS_REJECTED, **snapshot())

    def fail_closed_structure():
        return base(REASON_STRUCTURE, STATUS_REJECTED,
                    span_count=len(span_indices),
                    bounds_scope=None)

    def fail_closed_roundoff():
        return base(REASON_ROUNDOFF, STATUS_INDETERMINATE,
                    span_count=len(span_indices),
                    bounds_scope=None)

    prepared = []
    envelope_exceeded = False
    partition_unrepresentable = False
    for offset, span_index in enumerate(span_indices):
        u_start = knots[span_index]
        u_end = knots[span_index + 1]
        width = u_end - u_start
        speed = float(speed_bounds[offset])
        if not (math.isfinite(speed) and math.isfinite(width)
                and math.isfinite(u_start) and math.isfinite(u_end)):
            return fail_closed_structure()
        if width <= 0.0:                        # defensive: strict monotonicity was checked
            continue
        if not _span_midpoint_representable(u_start, u_end):
            return fail_closed_structure()
        roundoff = _parameter_roundoff_m(speed, u_start, u_end)
        if not math.isfinite(roundoff) or roundoff > FLOAT_GUARD_M:
            envelope_exceeded = True
        wanted = 1
        if speed > 0.0:
            ratio = speed * width / (2.0 * target_half_width)
            if not math.isfinite(ratio):
                return fail_closed_structure()
            wanted = int(math.ceil(ratio))
        wanted = max(1, wanted)
        predicted = min(wanted, int(max_nodes_per_span))
        if _interior_partition(u_start, u_end, predicted) is None:
            partition_unrepresentable = True
        prepared.append((span_index, u_start, u_end, width, speed, wanted))

    # Priority: unrepresentable midpoint already returned; envelope beats a
    # later n-partition collapse so large translations of representable
    # midpoints stay parameter_roundoff_exceeds_envelope.
    if envelope_exceeded:
        return fail_closed_roundoff()
    if partition_unrepresentable:
        return fail_closed_structure()

    preview = _Budget(max_evaluations=int(max_evaluations))
    for span_index, u_start, u_end, width, speed, wanted in prepared:
        granted, _truncated = preview.request(wanted, int(max_nodes_per_span))
        if granted < 1:
            break
        if _interior_partition(u_start, u_end, granted) is None:
            return fail_closed_structure()

    for span_index, u_start, u_end, width, speed, wanted in prepared:
        peak_speed = max(peak_speed, speed)
        granted, truncated = budget.request(wanted, int(max_nodes_per_span))
        if granted < 1:
            if unresolved_reason is None:
                unresolved_reason = REASON_WORK_CAP
                unresolved_span = span_index
            tolerance_met = False
            break
        samples = _interior_partition(u_start, u_end, granted)
        if samples is None:
            return fail_closed_structure()
        step = width / granted
        slack = speed * step / 2.0 + FLOAT_GUARD_M
        if not (math.isfinite(step) and math.isfinite(slack)):
            return reject_nonfinite()
        best_distance = math.inf
        best_inset = math.inf
        for u in samples:
            try:
                point = spline.position.evaluate(u)
            except (ValueError, OverflowError, ArithmeticError):
                return reject_nonfinite()
            if not _finite_point(point):
                return reject_nonfinite()
            distance = point_box_distance(point, obstacle_low, obstacle_high)
            inset = inward_face_clearance(point, map_low, map_high)
            if not (math.isfinite(distance) and math.isfinite(inset)):
                return reject_nonfinite()
            if distance < best_distance:
                best_distance = distance
            if inset < best_inset:
                best_inset = inset
        span_lower_obstacle = best_distance - slack
        span_upper_obstacle = best_distance + FLOAT_GUARD_M
        span_lower_inset = best_inset - slack
        span_upper_inset = best_inset + FLOAT_GUARD_M
        if not all(math.isfinite(value) for value in (
                span_lower_obstacle, span_upper_obstacle,
                span_lower_inset, span_upper_inset)):
            return reject_nonfinite()
        closed = (not truncated) and (
            slack + FLOAT_GUARD_M <= tolerance * (1.0 + 1e-12))
        if not closed:
            tolerance_met = False

        obstacle_lower = min(obstacle_lower, span_lower_obstacle)
        obstacle_upper = min(obstacle_upper, span_upper_obstacle)
        inset_lower = min(inset_lower, span_lower_inset)
        inset_upper = min(inset_upper, span_upper_inset)

        obstacle_fail = (span_upper_obstacle - radius) < required
        inset_fail = (span_upper_inset - radius) < required
        conclusive = obstacle_fail or inset_fail
        spans.append(SpanBracket(
            span_index=span_index,
            u_start=u_start,
            u_end=u_end,
            obstacle_lower=span_lower_obstacle,
            obstacle_upper=span_upper_obstacle,
            inset_lower=span_lower_inset,
            inset_upper=span_upper_inset,
            speed_bound=speed,
            nodes=granted,
            evaluations=granted,
            closed=closed,
            conclusive=conclusive,
        ))

        if conclusive and conclusive_reason is None:
            conclusive_reason = REASON_OBSTACLE if obstacle_fail else REASON_MAP
            binding_object = BINDING_OBJECT_OBSTACLE if obstacle_fail else BINDING_OBJECT_MAP_INSET
            binding_span = span_index

        span_ok = (span_lower_obstacle - radius) >= required and (span_lower_inset - radius) >= required
        if not (span_ok and closed) and unresolved_reason is None:
            unresolved_reason = REASON_BAND if closed else REASON_WORK_CAP
            unresolved_span = span_index

    common = snapshot()

    if conclusive_reason is not None:
        return base(conclusive_reason, STATUS_REJECTED,
                    binding_object=binding_object,
                    binding_span_index=binding_span,
                    binding_u_start=knots[binding_span] if binding_span is not None else None,
                    binding_u_end=knots[binding_span + 1] if binding_span is not None else None,
                    **common)

    if not spans:
        return base(REASON_NO_INTERVAL, STATUS_REJECTED, **common)

    if unresolved_reason is not None:
        # Fail closed: the proof did not close, so this is never an admission.
        return base(unresolved_reason, STATUS_INDETERMINATE,
                    binding_object=None,
                    binding_span_index=unresolved_span,
                    binding_u_start=knots[unresolved_span] if unresolved_span is not None else None,
                    binding_u_end=knots[unresolved_span + 1] if unresolved_span is not None else None,
                    **common)

    if inset_lower - radius <= obstacle_lower - radius:
        binding_object = BINDING_OBJECT_MAP_INSET
    else:
        binding_object = BINDING_OBJECT_OBSTACLE
    binding_span = min(spans, key=lambda span: (
        span.inset_lower if binding_object == BINDING_OBJECT_MAP_INSET else span.obstacle_lower,
        span.span_index)).span_index

    certificate = base(None, STATUS_ADMITTED,
                       admitted=True,
                       binding_object=binding_object,
                       binding_span_index=binding_span,
                       binding_u_start=knots[binding_span],
                       binding_u_end=knots[binding_span + 1],
                       **common)
    return certificate


__all__ = [
    "BINDING_OBJECT_MAP_INSET",
    "BINDING_OBJECT_OBSTACLE",
    "CANDIDATE_STATUS",
    "CERTIFICATE_REASONS",
    "DEFAULT_MAX_EVALUATIONS",
    "DEFAULT_MAX_NODES_PER_SPAN",
    "DEFAULT_TOLERANCE_M",
    "EVIDENCE_KIND",
    "ExactClearanceCertificate",
    "ExactClearanceError",
    "FLOAT_GUARD_M",
    "MAX_TOLERANCE_M",
    "NON_CLAIMS",
    "REASON_BAND",
    "REASON_DOMAIN",
    "REASON_KNOTS",
    "REASON_MAP",
    "REASON_NO_INTERVAL",
    "REASON_OBSTACLE",
    "REASON_ROUNDOFF",
    "REASON_STRUCTURE",
    "REASON_WORK_CAP",
    "BOUNDS_SCOPE_CURVE",
    "BOUNDS_SCOPE_PARTIAL",
    "STATUS_ADMITTED",
    "STATUS_INDETERMINATE",
    "STATUS_REJECTED",
    "SpanBracket",
    "certify_exact_clearance",
    "derivative_speed_bounds",
    "inward_face_clearance",
    "point_box_distance",
]
