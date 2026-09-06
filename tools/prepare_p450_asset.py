"""Extract pinned Prometheus P450 assets and convert STL to UE-frame OBJ.

Local Git reads by default; opt-in pinned STL downloads never populate Git objects.
No UE import, assembly placement, geometry repair, or physics change is performed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

COMMIT = "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce"
BASE = "Simulator/gazebo_simulator/gazebo_models/uav_models/p450"
SOURCES = {
    "meshes/p450.stl": "d8deef5854cc0568ff64cd5892130a349aaec71f",
    "meshes/p450_ccw.stl": "bb5753c6e2d37acee9adf6a049377538fab1b594",
    "meshes/p450_cw.stl": "8c78676df1f48fc8f84bcd0c060ba3050b28e355",
    "p450.sdf": "95104093b5480618073f6bb151eaab75ca2aba37",
    "model.config": "1f13c5c4cd7a54c4c455b6ff4460411994d36dca",
    "LICENSE": "7a61a72408bdc8967b8289d630a309e47b816fa7",
}
MAX_BYTES = 128 * 1024 * 1024
MAX_TRIANGLES = 1_000_000
FETCH_SECONDS = 45
SOCKET_SECONDS = 10
MESH_URLS = {name: f"https://raw.githubusercontent.com/amov-lab/Prometheus/{COMMIT}/{BASE}/{name}"
             for name in SOURCES if name.endswith(".stl")}
CONVENTION = {
    "source": "Gazebo X-forward, Y-left, Z-up; metres inferred from SDF scale 1 1 1",
    "target": "UE intended X-forward, Y-right, Z-up; centimetres",
    "position": "(x,y,z) -> (100*x,-100*y,100*z)",
    "winding": "(v0,v1,v2) -> (T(v0),T(v2),T(v1)); determinant(T)<0",
    "normals": "unit cross product of converted edges; source facet normals not trusted; zero-area faces retained without normals",
    "placement": "source mesh origins retained; no recentering, pose baking, extra scale or offset",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("asset download redirects are not permitted")


def fetch_mesh(relative):
    if relative not in MESH_URLS:
        raise ValueError("download path is not an allowed pinned mesh")
    started = time.monotonic()
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(MESH_URLS[relative], headers={"Accept-Encoding": "identity"})
    with opener.open(request, timeout=SOCKET_SECONDS) as response:
        if response.status != 200 or response.geturl() != MESH_URLS[relative]:
            raise ValueError("unexpected asset response")
        length = response.headers.get("Content-Length")
        if length is not None and not 0 < int(length) <= MAX_BYTES:
            raise ValueError("asset download exceeds size limit or is empty")
        raw = bytearray()
        while True:
            if time.monotonic() - started >= FETCH_SECONDS:
                raise TimeoutError("asset download deadline exceeded")
            chunk = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError("asset download exceeds size limit")
        if length is not None and len(raw) != int(length):
            raise ValueError("truncated asset download")
    raw = bytes(raw)
    if blob_sha1(raw) != SOURCES[relative]:
        raise ValueError(f"downloaded Git blob mismatch: {relative}")
    return raw


def normal(triangle):
    a, b, c = triangle
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    length = math.hypot(*cross)
    if not math.isfinite(length):
        raise ValueError("numerically unrepresentable triangle")
    if length == 0:
        return None
    return tuple(x / length for x in cross)


def parse_stl(data):
    """Strict lengths/grammar and finite values; preserve/report zero-area faces."""
    if len(data) > MAX_BYTES:
        raise ValueError("STL exceeds size limit")
    count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else None
    triangles = []
    if count is not None and len(data) == 84 + 50 * count:
        if not 0 < count <= MAX_TRIANGLES:
            raise ValueError("invalid triangle count")
        encoding = "binary"
        for offset in range(84, len(data), 50):
            values = struct.unpack_from("<12fH", data, offset)
            if not all(math.isfinite(x) for x in values[:12]):
                raise ValueError("non-finite STL value")
            triangles.append(tuple(tuple(values[i:i+3]) for i in (3, 6, 9)))
    else:
        encoding = "ascii"
        try:
            lines = [line.split() for line in data.decode("ascii").splitlines() if line.strip()]
        except UnicodeDecodeError as exc:
            raise ValueError("invalid binary length or non-ASCII STL") from exc
        if (len(lines) < 9 or lines[0][0] != "solid" or lines[-1][0] != "endsolid"
                or (len(lines)-2) % 7):
            raise ValueError("invalid ASCII STL structure or binary length")
        if not 0 < (len(lines)-2)//7 <= MAX_TRIANGLES:
            raise ValueError("invalid triangle count")
        for offset in range(1, len(lines)-1, 7):
            facet = lines[offset:offset+7]
            if (facet[0][:2] != ["facet", "normal"] or len(facet[0]) != 5
                    or facet[1] != ["outer", "loop"] or facet[5] != ["endloop"]
                    or facet[6] != ["endfacet"]
                    or any(len(row) != 4 or row[0] != "vertex" for row in facet[2:5])):
                raise ValueError("invalid ASCII facet")
            values = [float(x) for row in [facet[0][2:]] + [r[1:] for r in facet[2:5]] for x in row]
            if not all(math.isfinite(x) for x in values):
                raise ValueError("non-finite STL value")
            triangles.append(tuple(tuple(values[i:i+3]) for i in (3, 6, 9)))
    for triangle in triangles:
        normal(triangle)
    return triangles, encoding


def transform(point):
    return (100 * point[0], -100 * point[1], 100 * point[2])


def bounds(triangles):
    points = [p for triangle in triangles for p in triangle]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return {"min": low, "max": high, "size": [high[i]-low[i] for i in range(3)]}


def convert_obj(triangles, source):
    converted = [tuple(transform(t[i]) for i in (0, 2, 1)) for t in triangles]
    def fmt(values):
        return " ".join(format(0.0 if x == 0 else x, ".17g") for x in values)
    lines = ["# Modified from Prometheus " + COMMIT + ":" + source,
             "# AMOVLAB P450; model.config author BOSHEN97; see ../raw/LICENSE",
             "# Converted m to cm, reflected Y, reversed winding; original mesh origin retained."]
    normal_index = 0
    for index, triangle in enumerate(converted):
        lines.extend("v " + fmt(p) for p in triangle)
        face_normal = normal(triangle)
        if face_normal is None:
            lines.append("# Source zero-area face retained; no defined normal")
            lines.append("f " + " ".join(str(index*3+j) for j in (1, 2, 3)))
        else:
            normal_index += 1
            lines.append("vn " + fmt(face_normal))
            lines.append("f " + " ".join(f"{index*3+j}//{normal_index}" for j in (1, 2, 3)))
    return ("\n".join(lines) + "\n").encode("ascii"), bounds(converted)


def sdf_metadata(data):
    model = ET.fromstring(data).find("model")
    visuals = []
    rotors = []
    for link in model.findall("link"):
        for visual in link.findall("visual"):
            mesh = visual.find("geometry/mesh")
            if mesh is None:
                continue
            scale = [float(x) for x in mesh.findtext("scale", "1 1 1").split()]
            if scale != [1, 1, 1]:
                raise ValueError("unexpected SDF mesh scale")
            visuals.append({"link": link.get("name"), "visual": visual.get("name"),
                            "mesh_uri": mesh.findtext("uri"), "scale": scale,
                            "link_pose_m_rad": link.findtext("pose"),
                            "visual_pose_m_rad": visual.findtext("pose")})
    for plugin in model.findall("plugin"):
        direction = plugin.findtext("turningDirection")
        if direction is None:
            continue
        name = plugin.findtext("linkName")
        visual = next(v for v in visuals if v["link"] == name)
        pose = [float(x) for x in visual["link_pose_m_rad"].split()]
        rotors.append({"link": name, "joint": plugin.findtext("jointName"),
                       "motor_number": int(plugin.findtext("motorNumber")),
                       "source_turning_direction": direction, "mesh_uri": visual["mesh_uri"],
                       "source_pose_m_rad": pose, "ue_translation_cm_unapplied": transform(pose[:3])})
    return {"visuals": visuals, "rotors": rotors,
            "included_models_not_extracted": [node.findtext("uri") for node in model.findall("include")]}


def git_read(repo, *args, input_data=None):
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=60, input=input_data).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError("Local Git read failed (automatic fetching disabled): "
                         + " ".join(args) + ": " + exc.stderr.decode("utf-8", errors="replace").strip()) from exc


def read_source(repo, relative, fetch_missing=False):
    expected = SOURCES[relative]
    source = "LICENSE" if relative == "LICENSE" else f"{BASE}/{relative}"
    info = git_read(repo, "cat-file", "--batch-check", input_data=(expected + "\n").encode()).decode().strip()
    if info == f"{expected} missing":
        if not fetch_missing or relative not in MESH_URLS:
            raise ValueError(f"local Git blob missing: {source}; pinned mesh download requires --fetch-missing")
        return fetch_mesh(relative), MESH_URLS[relative]
    parts = info.split()
    if len(parts) != 3 or parts[:2] != [expected, "blob"]:
        raise ValueError(f"unexpected Git object information: {info}")
    size = int(parts[2])
    if not 0 < size <= MAX_BYTES:
        raise ValueError("source exceeds size limit or is empty")
    raw = git_read(repo, "show", f"{COMMIT}:{source}")
    if len(raw) != size or blob_sha1(raw) != expected:
        raise ValueError(f"source blob mismatch: {source}")
    return raw, "local_git"


def prepare(repo, output, fetch_missing=False):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"refusing existing output: {output}")
    files = {}
    records = []
    for relative, expected in SOURCES.items():
        source = "LICENSE" if relative == "LICENSE" else f"{BASE}/{relative}"
        tree = git_read(repo, "ls-tree", COMMIT, "--", source).decode("utf-8").strip()
        if tree.split("\t") != [f"100644 blob {expected}", source] and tree.split("\t") != [f"100755 blob {expected}", source]:
            raise ValueError(f"unexpected source tree entry: {source}")
        raw, acquisition = read_source(repo, relative, fetch_missing)
        blob = blob_sha1(raw)
        if blob != expected:
            raise ValueError(f"source blob mismatch: {source}")
        raw_path = f"raw/{relative}"
        files[raw_path] = raw
        record = {"source_path": source, "source_commit": COMMIT, "git_blob": blob,
                  "raw_path": raw_path, "raw_sha256": sha256(raw), "raw_bytes": len(raw),
                  "acquisition": acquisition}
        if relative.endswith(".stl"):
            triangles, encoding = parse_stl(raw)
            obj, after = convert_obj(triangles, source)
            obj_path = "obj/" + Path(relative).stem + ".obj"
            files[obj_path] = obj
            record.update(stl_encoding=encoding, triangles=len(triangles),
                          source_zero_area_triangles=sum(normal(t) is None for t in triangles),
                          converted_zero_area_triangles=sum(normal(tuple(transform(t[i]) for i in (0, 2, 1))) is None for t in triangles),
                          original_header_hex=raw[:80].hex() if encoding == "binary" else None,
                          original_header_text=(raw[:80] if encoding == "binary" else raw.splitlines()[0]).decode("ascii", errors="backslashreplace"),
                          source_bounds_m=bounds(triangles), converted_bounds_cm=after,
                          obj_path=obj_path, obj_sha256=sha256(obj), obj_bytes=len(obj))
        records.append(record)
    config = ET.fromstring(files["raw/model.config"])
    manifest = {"schema_version": 1, "source_repository": "https://github.com/amov-lab/Prometheus",
                "source_commit": COMMIT, "conversion": CONVENTION, "files": records,
                "sdf": sdf_metadata(files["raw/p450.sdf"]),
                "model_author": config.findtext("author/name"),
                "license_evidence": "Pinned root LICENSE: Apache 2.0, Copyright 2022 AMOVLAB. No mesh-specific license found in inspected model tree; not an independent authorship audit.",
                "ue_import_verified": False}
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    # Validate every input and conversion before creating anything. Never overwrite.
    output.mkdir(parents=False, exist_ok=False)
    for relative, content in files.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(content)
    for relative, content in files.items():
        if (output / relative).read_bytes() != content:
            raise OSError(f"output verification failed: {relative}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path, help="new directory; parent must exist")
    parser.add_argument("--fetch-missing", action="store_true", help="allow only pinned raw GitHub STL downloads when local blobs are missing")
    args = parser.parse_args()
    try:
        manifest = prepare(args.repo, args.output, args.fetch_missing)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps({"output": str(args.output), "meshes": [r for r in manifest["files"] if "triangles" in r]}, indent=2))


if __name__ == "__main__":
    main()
