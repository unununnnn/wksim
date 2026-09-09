#!/usr/bin/env python3
"""Save/export/import and run the isolated mass-configurable Quad X model."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Simulator"))
from wksim_core.model_parameters import (ARCHIVE, ConfiguredModel, build_configured_model,
                                        load_config, make_config, save_config, sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    new = sub.add_parser("new", help="save a complete named config; defaults to 1.515 kg")
    new.add_argument("output", type=Path)
    new.add_argument("--name", default="quad-x-default")
    new.add_argument("--mass-kg", type=float, default=1.515)
    edit = sub.add_parser("edit", help="import, change mass/name and save to a new file")
    edit.add_argument("config", type=Path)
    edit.add_argument("output", type=Path)
    edit.add_argument("--name", required=True)
    edit.add_argument("--mass-kg", type=float, required=True)
    export = sub.add_parser("export", aliases=["import"], help="validate config and save it unchanged to a new file")
    export.add_argument("config", type=Path)
    export.add_argument("output", type=Path)
    inspect = sub.add_parser("inspect", help="import and print the complete validated identity")
    inspect.add_argument("config", type=Path)
    build = sub.add_parser("build", help="build in a fresh local /tmp directory")
    build.add_argument("config", type=Path)
    build.add_argument("--archive", type=Path, default=ARCHIVE)
    run = sub.add_parser("run", help="fresh process: check identity/mass, then apply four commands")
    run.add_argument("config", type=Path)
    run.add_argument("library", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--commands", nargs=4, type=float, required=True)
    run.add_argument("--ticks", type=int, default=500, choices=range(1, 1001), metavar="1..1000")
    args = parser.parse_args()
    if args.action == "new":
        config = make_config(args.name, args.mass_kg)
        save_config(config, args.output)
    else:
        config = load_config(args.config)
        if args.action == "edit":
            config = make_config(args.name, args.mass_kg)
            save_config(config, args.output)
        elif args.action in ("export", "import"):
            save_config(config, args.output)
        elif args.action == "build":
            print(build_configured_model(config, args.archive))
            return
        elif args.action == "run":
            commands = args.commands + [0.] * 12
            # Preserve interrupted/failed runs, too. Never overwrite prior evidence.
            with args.output.open("x", encoding="utf-8") as stream:
                with ConfiguredModel(args.library, config) as model:
                    stream.write(json.dumps({"config": config, "applied_mass_kg_before_step": model.applied_mass_kg,
                                             "library": str(args.library), "library_sha256": sha(args.library.read_bytes()),
                                             "commands": commands, "requested_ticks": args.ticks}) + "\n")
                    for tick in range(1, args.ticks + 1):
                        stream.write(json.dumps({"tick": tick, "output120": model.step(commands)}, allow_nan=False) + "\n")
            print(args.output)
            return
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
