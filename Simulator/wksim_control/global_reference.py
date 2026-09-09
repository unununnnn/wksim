# SPDX-License-Identifier: Apache-2.0
"""Pure global-home-v1 boundary; no clock, ROS, flight or implicit local fallback.

Call resolve with the session's last command ID and previous observations.
Before EVERY publish call validate_current, retaining its returned checkpoint.
On any Rejection the host must discard its target; clock rollback invalidates
the session until a new control epoch. The host owns this persistent latch,
pause/resume invalidation, native subscriptions and datum-proof verification.
"""
from dataclasses import dataclass, replace
import math
import struct

SCHEMA = 'global-home-v1'
RADIUS = 6371000.0
AP_SCALE = 0.011131884502145034
TTL = 2.0


class Rejection(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def require(condition, reason):
    if not condition:
        raise Rejection(reason)


def number(value):
    require(type(value) in (int, float), 'invalid_number')
    try:
        require(math.isfinite(value), 'invalid_number')
    except OverflowError:
        raise Rejection('invalid_number') from None
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'invalid_integer')


def f32(value):
    number(value)
    try:
        result = struct.unpack('f', struct.pack('f', value))[0]
    except (OverflowError, struct.error):
        raise Rejection('native_range') from None
    require(math.isfinite(result), 'native_range')
    return result


def coordinates(lat, lon):
    require(abs(number(lat)) <= 85 and -180 <= number(lon) <= 180, 'coordinate_range')
    return lat, -180.0 if lon == 180 else lon


@dataclass(frozen=True)
class Identity:
    stack: str
    run_id: str
    instance_id: str
    vehicle_id: int
    control_epoch: int
    native_session: str
    publisher_gid: str
    scene_origin_id: str


@dataclass(frozen=True)
class HomeSnapshot:
    schema: str
    identity: Identity
    source_timestamp: int
    received_monotonic: float
    home_generation: int
    latitude_deg: float
    longitude_deg: float
    alt_amsl_m: float
    datum_proof_id: str
    valid_hpos: bool
    valid_alt: bool
    valid_lpos: bool
    update_count: int | None
    manual_home: bool | None
    ap_raw: tuple | None


@dataclass(frozen=True)
class OriginSnapshot:
    identity: Identity
    origin_id: str
    local_origin_generation: int
    ref_timestamp: int
    latitude_deg: float
    longitude_deg: float
    alt_amsl_m: float
    global_reset_counters: tuple
    local_reset_counters: tuple
    source_timestamp: int
    received_monotonic: float
    navigation_valid: bool
    datum_proof_id: str


@dataclass(frozen=True)
class GlobalCommand:
    schema: str
    latitude_deg: float
    longitude_deg: float
    height_m: float
    height_reference: str
    identity: Identity
    home_generation: int
    origin_id: str
    local_origin_generation: int
    command_id: int
    issued_monotonic: float
    expires_monotonic: float


@dataclass(frozen=True)
class ResolvedTarget:
    original: GlobalCommand
    home: HomeSnapshot
    origin: OriginSnapshot
    height_amsl_m: float
    height_relative_m: float
    native_kind: str
    native_target: tuple
    check_enu_m: tuple
    algorithm: str
    validated_monotonic: float


def project(lat0, lon0, lat, lon):
    """PX4 MapProjection::project, unquantized north/east in metres."""
    coordinates(lat0, lon0)
    coordinates(lat, lon)
    p0, p = math.radians(lat0), math.radians(lat)
    dl = math.radians(lon) - math.radians(lon0)
    s0, c0, s, c = math.sin(p0), math.cos(p0), math.sin(p), math.cos(p)
    angle = math.acos(max(-1.0, min(1.0, s0*s + c0*c*math.cos(dl))))
    k = 1.0 if angle == 0 else angle / math.sin(angle)
    return k*RADIUS*(c0*s-s0*c*math.cos(dl)), k*RADIUS*c*math.sin(dl)


def reproject(lat0, lon0, north, east):
    """Inverse spherical projection, for bounded numeric coordinate checks."""
    coordinates(lat0, lon0)
    n, e = number(north)/RADIUS, number(east)/RADIUS
    c = math.hypot(n, e)
    require(math.hypot(north, east) <= 100, 'horizontal_range')
    if c == 0:
        return coordinates(lat0, lon0)
    p0 = math.radians(lat0)
    p = math.asin(math.cos(c)*math.sin(p0) + n*math.sin(c)*math.cos(p0)/c)
    dl = math.atan2(e*math.sin(c), c*math.cos(p0)*math.cos(c)-n*math.sin(p0)*math.sin(c))
    return coordinates(math.degrees(p), (lon0+math.degrees(dl)+180) % 360-180)


def ap_distance(home_raw, target_raw):
    """Pinned Location float N/E/D arithmetic, returned as ENU."""
    lat, lon, alt = home_raw
    tlat, tlon, talt = target_raw
    delta = (tlon-lon+1800000000) % 3600000000-1800000000
    midpoint = math.trunc((lat+tlat)/2)
    scale = f32(math.cos(f32(midpoint*(1.0e-7*(math.pi/180)))))
    east = f32(f32(f32(delta)*f32(AP_SCALE))*scale)
    north = f32(f32(tlat-lat)*f32(AP_SCALE))
    return east, north, -f32((alt-talt)*0.01)


def _identity(identity):
    require(type(identity) is Identity, 'identity_invalid')
    require(identity.stack in ('px4', 'arducopter'), 'stack_unsupported')
    for value in (identity.run_id, identity.instance_id, identity.native_session,
                  identity.publisher_gid, identity.scene_origin_id):
        require(type(value) is str and bool(value.strip()), 'identity_invalid')
    integer(identity.vehicle_id, 1)
    integer(identity.control_epoch)


def _fresh(snapshot, now, previous):
    integer(snapshot.source_timestamp, 1)
    require(0 <= now-number(snapshot.received_monotonic) <= TTL, 'snapshot_stale')
    if previous is not None:
        require(snapshot.source_timestamp >= previous.source_timestamp, 'source_clock_regressed')
        require(snapshot.received_monotonic >= previous.received_monotonic, 'clock_regressed')
        if snapshot.source_timestamp == previous.source_timestamp:
            require(snapshot == previous, 'duplicate_source_changed')


def _snapshots(home, origin, now, previous_home=None, previous_origin=None):
    number(now)
    require(type(home) is HomeSnapshot and type(origin) is OriginSnapshot, 'snapshot_invalid')
    require(home.schema == SCHEMA, 'schema_unsupported')
    _identity(home.identity)
    require(home.identity == origin.identity, 'identity_mismatch')
    for snapshot in (home, origin):
        coordinates(snapshot.latitude_deg, snapshot.longitude_deg)
        number(snapshot.alt_amsl_m)
        require(type(snapshot.datum_proof_id) is str and bool(snapshot.datum_proof_id.strip()), 'datum_unverified')
    for flag in (home.valid_hpos, home.valid_alt, home.valid_lpos, origin.navigation_valid):
        require(type(flag) is bool, 'invalid_flag')
    require(home.valid_hpos and home.valid_alt and origin.navigation_valid, 'navigation_invalid')
    integer(home.home_generation, 1)
    integer(origin.local_origin_generation, 1)
    integer(origin.ref_timestamp, 1)
    require(type(origin.origin_id) is str and bool(origin.origin_id.strip()), 'origin_invalid')
    for counters in (origin.global_reset_counters, origin.local_reset_counters):
        require(type(counters) is tuple and len(counters) > 0, 'reset_identity_invalid')
        for value in counters:
            integer(value)
    if home.identity.stack == 'px4':
        integer(home.update_count)
        require(home.update_count <= 255 and type(home.manual_home) is bool and home.ap_raw is None, 'home_native_invalid')
    else:
        require(home.update_count is None and home.manual_home is None, 'home_native_invalid')
        require(type(home.ap_raw) is tuple and len(home.ap_raw) == 3, 'home_native_invalid')
        require(all(type(v) is int and -2147483648 <= v <= 2147483647 for v in home.ap_raw), 'home_native_invalid')
        require(home.ap_raw[0]/1e7 == home.latitude_deg and
                coordinates(0, home.ap_raw[1]/1e7)[1] == coordinates(0, home.longitude_deg)[1] and
                home.ap_raw[2]/100 == home.alt_amsl_m, 'home_native_mismatch')
    _fresh(home, now, previous_home)
    _fresh(origin, now, previous_origin)


def _home_key(home):
    return replace(home, source_timestamp=1, received_monotonic=0)


def _origin_key(origin):
    return replace(origin, source_timestamp=1, received_monotonic=0)


def _command(command, home, origin, now):
    require(type(command) is GlobalCommand and command.schema == SCHEMA, 'schema_unsupported')
    _identity(command.identity)
    require(command.identity == home.identity, 'identity_mismatch')
    integer(command.home_generation, 1)
    integer(command.local_origin_generation, 1)
    integer(command.command_id, 1)
    require(command.home_generation == home.home_generation, 'home_changed')
    require((command.origin_id, command.local_origin_generation) ==
            (origin.origin_id, origin.local_origin_generation), 'origin_changed')
    issued, expires = number(command.issued_monotonic), number(command.expires_monotonic)
    require(0 < expires-issued <= TTL and issued <= now <= expires, 'command_expired')
    coordinates(command.latitude_deg, command.longitude_deg)
    number(command.height_m)
    require(command.height_reference in ('home_relative', 'amsl'), 'height_reference_unsupported')


def resolve(command, *, now, home, origin, last_command_id,
            previous_home=None, previous_origin=None, paused=False):
    """Resolve an explicitly bound command. No defaults for identity or datum."""
    require(paused is False, 'paused')
    _snapshots(home, origin, now, previous_home, previous_origin)
    _command(command, home, origin, now)
    integer(last_command_id)
    require(command.command_id > last_command_id, 'command_id_not_increasing')
    relative = (command.height_m if command.height_reference == 'home_relative'
                else command.height_m-home.alt_amsl_m)
    absolute = (home.alt_amsl_m+relative if command.height_reference == 'home_relative'
                else command.height_m)
    require(abs(relative) <= 100, 'height_range')
    lat, lon = coordinates(command.latitude_deg, command.longitude_deg)
    require(math.hypot(*project(home.latitude_deg, home.longitude_deg, lat, lon)) <= 100, 'horizontal_range')
    if home.identity.stack == 'px4':
        north, east = project(origin.latitude_deg, origin.longitude_deg, lat, lon)
        require(math.hypot(north, east) <= 100, 'horizontal_range')
        native = tuple(f32(v) for v in (north, east, origin.alt_amsl_m-absolute))
        require(math.hypot(*native[:2]) <= 100, 'horizontal_range')
        qlat, qlon = reproject(origin.latitude_deg, origin.longitude_deg, *native[:2])
        require(math.hypot(*project(home.latitude_deg, home.longitude_deg, qlat, qlon)) <= 100, 'horizontal_range')
        require(abs(origin.alt_amsl_m-native[2]-home.alt_amsl_m) <= 100, 'height_range')
        enu, kind, algorithm = (native[1], native[0], -native[2]), 'trajectory_setpoint_ned', 'px4-map-projection-v1'
    else:
        delta_lon = (lon-home.longitude_deg+180) % 360-180
        midpoint = math.radians((lat+home.latitude_deg)/2)
        require(math.hypot((lat-home.latitude_deg)*1e7*AP_SCALE,
                           delta_lon*1e7*AP_SCALE*math.cos(midpoint)) <= 100, 'horizontal_range')
        wire_alt = f32(relative)
        native = (int(lat*1e7), int(lon*1e7), int(wire_alt*100))
        absolute_cm = home.ap_raw[2]+native[2]
        require(-2147483648 <= absolute_cm <= 2147483647, 'native_range')
        require(abs(wire_alt) <= 100 and abs(native[2]/100) <= 100, 'height_range')
        require(math.hypot(*project(home.latitude_deg, home.longitude_deg, native[0]/1e7, native[1]/1e7)) <= 100, 'horizontal_range')
        enu = ap_distance(home.ap_raw, (native[0], native[1], absolute_cm))
        require(math.hypot(*enu[:2]) <= 100, 'horizontal_range')
        kind, algorithm = 'FRAME_GLOBAL_REL_ALT', 'ap-location-v1'
    return ResolvedTarget(command, home, origin, absolute, relative, kind, native, enu, algorithm, now)


def validate_current(target, *, now, home, origin, paused=False):
    """Return refreshed checkpoint; rejection requires host to discard target."""
    require(type(target) is ResolvedTarget, 'target_invalid')
    require(paused is False, 'paused')
    require(number(now) >= target.validated_monotonic, 'clock_regressed')
    _snapshots(home, origin, now, target.home, target.origin)
    require(_home_key(home) == _home_key(target.home), 'home_changed')
    require(_origin_key(origin) == _origin_key(target.origin), 'origin_changed')
    _command(target.original, home, origin, now)
    return replace(target, home=home, origin=origin, validated_monotonic=now)
