"""Emit an apply_patch for the pinned Prometheus interfaces, or verify the port.

Read-only: this program never writes source files. Apply its --patch output with
apply_patch. The original ROS1 package remains the provenance/compatibility base.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parent.parent
UPSTREAM = "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce"
SOURCE = REPO / "Modules/common/prometheus_msgs"
TARGET = REPO / "ros2/src/prometheus_msgs"
TYPE_ALIASES = {"Header": "std_msgs/Header", "time": "builtin_interfaces/Time", "duration": "builtin_interfaces/Duration"}
NAME_OVERRIDES = {("BoundingBox.msg", "Class"): "class_name"}


def snake(name):
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"_+", "_", name).lower()


def convert(source, filename):
    output, changes, seen = [], [], set()
    section = 0
    for number, line in enumerate(source.splitlines(), 1):
        code, mark, comment = line.partition("#")
        code = code.strip()
        if not code or code == "---":
            output.append(line.rstrip())
            if code == "---":
                section += 1
                seen.clear()
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_/]*(?:\[\d*\])?)\s+([A-Za-z][A-Za-z0-9_]*)(\s*(?:=.*)?)", code)
        if not match:
            raise ValueError(f"Unsupported upstream declaration {filename}:{number}: {code}")
        source_type, name, value = match.groups()
        constant = value.strip().startswith("=")
        renamed = snake(name).upper() if constant else NAME_OVERRIDES.get((filename, name), snake(name))
        pattern = r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*" if constant else r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
        if not re.fullmatch(pattern, renamed) or renamed in seen:
            raise ValueError(f"Invalid or colliding migrated name {filename}:{number}: {renamed}")
        seen.add(renamed)
        base, bracket, array = source_type.partition("[")
        converted_type = TYPE_ALIASES.get(base, base) + (bracket + array if bracket else "")
        output.append(f"{converted_type} {renamed}{value}" + (f"  #{comment}" if mark else ""))
        if source_type != converted_type or renamed != name:
            changes.append(dict(line=number, section=section, kind="constant" if constant else "field",
                                source_type=source_type, target_type=converted_type, source_name=name, target_name=renamed))
    notice = ("# Copyright 2022 AMOVLAB. SPDX-License-Identifier: Apache-2.0\n"
              f"# wksim ROS2 migration of Prometheus {UPSTREAM[:12]}: {filename}.\n"
              "# Naming/type aliases changed; see UPSTREAM.json. Original comments retained.\n")
    return notice + "\n".join(output).rstrip() + "\n", changes


def expected_files():
    # Refuse to silently regenerate from a changed/incomplete baseline.
    prefix = SOURCE.relative_to(REPO).as_posix() + "/"
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", UPSTREAM, "--", prefix], cwd=REPO, text=True).splitlines()
    names = sorted(p[len(prefix):] for p in tracked if p.endswith((".msg", ".srv", ".action")))
    local = sorted(p.relative_to(SOURCE).as_posix() for kind in ("msg", "srv", "action") for p in (SOURCE/kind).glob("*"))
    if names != local:
        raise ValueError("Local interface inventory differs from the pinned upstream tree")
    files, provenance = {}, []
    for relative in names:
        path = SOURCE/relative
        source_bytes = path.read_bytes()
        original = subprocess.check_output(["git", "show", f"{UPSTREAM}:{prefix}{relative}"], cwd=REPO)
        if source_bytes.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
            raise ValueError(f"Upstream interface was edited: {relative}")
        migrated, changes = convert(source_bytes.decode("utf-8"), path.name)
        files[relative] = migrated
        provenance.append(dict(file=relative, upstream_sha256=hashlib.sha256(original).hexdigest(),
                               source_lf_sha256=hashlib.sha256(source_bytes.replace(b"\r\n", b"\n")).hexdigest(),
                               migrated_sha256=hashlib.sha256(migrated.encode()).hexdigest(), changes=changes))
    files["UPSTREAM.json"] = json.dumps(dict(repository="https://github.com/amov-lab/Prometheus", commit=UPSTREAM,
        source_package="Modules/common/prometheus_msgs", license="Apache-2.0 (repository LICENSE; upstream package.xml says TODO)",
        compatibility="Source-semantic migration, not ROS1 wire compatibility. ROS2 Header has no seq; builtin Time.sec is int32.",
        interfaces=provenance), ensure_ascii=False, indent=2) + "\n"
    files["LICENSE"] = (REPO/"LICENSE").read_text(encoding="utf-8").rstrip("\n") + "\n"
    listing = "\n".join(f'  "{name}"' for name in names)
    files["CMakeLists.txt"] = f'''cmake_minimum_required(VERSION 3.8)
project(prometheus_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
rosidl_generate_interfaces(${{PROJECT_NAME}}
{listing}
  DEPENDENCIES builtin_interfaces std_msgs geometry_msgs sensor_msgs
)
ament_export_dependencies(rosidl_default_runtime)
install(FILES UPSTREAM.json LICENSE DESTINATION share/${{PROJECT_NAME}})
ament_package()
'''
    files["package.xml"] = '''<?xml version="1.0"?>
<package format="3">
  <name>prometheus_msgs</name>
  <version>0.1.0</version>
  <description>ROS2 migration of the pinned AMOVLAB Prometheus interfaces; see UPSTREAM.json.</description>
  <maintainer email="unununnnn@users.noreply.github.com">wksim maintainers</maintainer>
  <author>AMOVLAB and Prometheus contributors</author>
  <license>Apache-2.0</license>
  <buildtool_depend>ament_cmake</buildtool_depend>
  <build_depend>rosidl_default_generators</build_depend>
  <exec_depend>rosidl_default_runtime</exec_depend>
  <depend>builtin_interfaces</depend>
  <depend>std_msgs</depend>
  <depend>geometry_msgs</depend>
  <depend>sensor_msgs</depend>
  <member_of_group>rosidl_interface_packages</member_of_group>
  <export><build_type>ament_cmake</build_type></export>
</package>
'''
    return files, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", action="store_true")
    args = parser.parse_args()
    files, provenance = expected_files()
    if args.patch:
        if TARGET.exists():
            parser.error("Refusing to overwrite an existing ROS2 package; inspect changes manually")
        print("*** Begin Patch")
        for relative, content in files.items():
            print(f"*** Add File: {(TARGET/relative).as_posix()}")
            print("\n".join("+" + line for line in content.splitlines()))
        print("*** End Patch")
    else:
        mismatches = [name for name, expected in files.items() if not (TARGET/name).is_file()
                      or (TARGET/name).read_text(encoding="utf-8") != expected]
        extra = [str(p.relative_to(TARGET)) for kind in ("msg", "srv", "action") for p in (TARGET/kind).glob("*")
                 if p.relative_to(TARGET).as_posix() not in files]
        result = dict(status="pass" if not mismatches and not extra else "failed", commit=UPSTREAM,
                      counts={kind:sum(p["file"].startswith(kind + "/") for p in provenance) for kind in ("msg", "srv", "action")},
                      declarations_changed=sum(len(p["changes"]) for p in provenance), mismatches=mismatches, extra=extra)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "pass" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
