"""Offline structural map for the e0 model's 6DOF continuous-state integrators.

Read-only metadata extraction: opens the frozen SLX (a ZIP of system XML) and the
bound Aerospace Blockset 6DOF libraries and reports block names / SIDs / SHA-256
only. It never copies model or vendor source, never runs MATLAB, and never
overwrites an existing report.

The runtime addressability of the library-linked 6DOF integrator blocks is NOT
decidable offline; the reference probe resolves them in the running model. This
tool only pins the static structure (entry points + library integrator SIDs).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = REPO / 'validation' / 'numerical-conformance-gxxh6xhr' / 'C3G' / 'staged-model' / 'Exp1_MinModelTemp.slx'
DEFAULT_OUT = REPO / 'validation' / 'coordination' / 'g6-reference-probe-20260913'

# Root-level typed I/O the reference probe binds to (names in the frozen model).
IO_BLOCKS = ('inPWMs', 'TerrainIn15d', 'HILSensor30d', 'HILGPS30d', 'VehileInfo60d')


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _system_xmls(zf):
    """Map system xml member name -> parsed <System> root element."""
    out = {}
    for name in zf.namelist():
        if name.startswith('simulink/systems/') and name.endswith('.xml'):
            out[name] = ET.fromstring(zf.read(name))
    return out


def _blocks(system_elem):
    """Direct-child <Block> elements as dicts of block_type/name/sid/props."""
    blocks = []
    for block in system_elem.findall('Block'):
        props = {}
        for p in block.findall('P'):
            if p.get('Name'):
                props[p.get('Name')] = p.text
        blocks.append({
            'block_type': block.get('BlockType'),
            'name': ' '.join((block.get('Name') or '').split()),
            'sid': block.get('SID'),
            'props': props,
        })
    return blocks


def _find_blocks(systems, predicate):
    """Yield (system_member, block) for blocks matching predicate across systems."""
    for member, elem in systems.items():
        for block in _blocks(elem):
            if predicate(block):
                yield member, block


def map_reference_blocks(model_slx, libraries=None):
    """Extract the static structural map; metadata (names/SIDs/SHA-256) only."""
    model_slx = Path(model_slx)
    with zipfile.ZipFile(model_slx) as zf:
        systems = _system_xmls(zf)
    model_name = model_slx.stem
    root_member = 'simulink/systems/system_root.xml'
    if root_member not in systems:
        raise ValueError('model SLX has no system_root.xml: ' + str(model_slx))

    # The model's actual I/O ports are the ROOT-level Inport/Outport blocks; the
    # same names recur inside subsystems as boundary outports, so search root only.
    root_blocks = _blocks(systems[root_member])
    io_blocks = {}
    for name in IO_BLOCKS:
        matches = [b for b in root_blocks if b['name'] == name]
        if len(matches) != 1:
            raise ValueError('expected exactly one root block named ' + name)
        b = matches[0]
        io_blocks[name] = {'block_type': b['block_type'], 'sid': b['sid'],
                           'path': model_name + '/' + name}

    sixdof_refs = [b for _, b in _find_blocks(
        systems, lambda b: b['block_type'] == 'Reference'
        and ('6dof' in (b['props'].get('SourceBlock') or '').lower()
             or '6dof' in (b['props'].get('SourceType') or '').lower()))]
    if len(sixdof_refs) != 1:
        raise ValueError('expected exactly one 6DOF reference block')
    sixdof = sixdof_refs[0]

    # The subsystem that contains the 6DOF reference (its own system_<sid>.xml).
    sixdof_subsystem = None
    for member, elem in systems.items():
        for block in _blocks(elem):
            if block['block_type'] == 'SubSystem' and block['sid']:
                child = 'simulink/systems/system_{}.xml'.format(block['sid'])
                if child in systems and any(b['sid'] == sixdof['sid'] for _, b in
                                            _find_blocks({child: systems[child]}, lambda b: True)):
                    sixdof_subsystem = {'name': block['name'], 'sid': block['sid']}
                    break
        if sixdof_subsystem is not None:
            break

    model_integrators = [
        {'name': b['name'], 'sid': b['sid'], 'system': member}
        for member, b in _find_blocks(systems, lambda b: b['block_type'] == 'Integrator')]

    lib_out = {}
    for lib_name, lib_path in (libraries or {}).items():
        lib_path = Path(lib_path)
        with zipfile.ZipFile(lib_path) as zf:
            lib_systems = _system_xmls(zf)
        integrators = [{'name': b['name'], 'sid': b['sid'], 'system': member}
                       for member, b in _find_blocks(lib_systems, lambda b: b['block_type'] == 'Integrator')]
        lib_out[lib_name] = {'path': str(lib_path), 'sha256': _sha256(lib_path),
                             'integrators': integrators}

    return {
        'model_slx': str(model_slx),
        'model_slx_sha256': _sha256(model_slx),
        'model_name': model_name,
        'io': io_blocks,
        'sixdof': {
            'subsystem': sixdof_subsystem,
            'reference': {'name': sixdof['name'], 'sid': sixdof['sid'],
                          'source_block': sixdof['props'].get('SourceBlock'),
                          'source_type': sixdof['props'].get('SourceType')},
        },
        'model_integrators': model_integrators,
        'libraries': lib_out,
        'note': ('Continuous-state integrators of the rigid-body 6DOF live inside the '
                 'library-linked Aerospace Blockset block (source_block above), not directly '
                 'in the model XML. Their full runtime paths through the library link are '
                 'resolved by the reference probe in the running model, not decidable offline.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--library', action='append', default=[],
                        help='name=path for a bound 6DOF library SLX (repeatable)')
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--no-write', action='store_true')
    args = parser.parse_args(argv)

    libraries = {}
    for spec in args.library:
        name, sep, path = spec.partition('=')
        if not sep:
            raise ValueError('--library expects name=path: ' + spec)
        libraries[name] = path
    mapping = map_reference_blocks(args.model, libraries)

    print('reference-block map (offline, metadata only)')
    print('  model   : {} sha256={}'.format(mapping['model_name'], mapping['model_slx_sha256']))
    print('  io      : {}'.format({k: v['sid'] for k, v in mapping['io'].items()}))
    print('  6dof    : {} ({}) <- {}'.format(
        mapping['sixdof']['reference']['name'], mapping['sixdof']['reference']['sid'],
        mapping['sixdof']['reference']['source_block']))
    for name, lib in mapping['libraries'].items():
        print('  library : {} sha256={} integrators={}'.format(
            name, lib['sha256'], [(i['name'], i['sid']) for i in lib['integrators']]))

    if args.no_write:
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / 'block-map.json'
    if os.path.lexists(target):
        print('Block map output already exists; refusing to overwrite: ' + str(target),
              file=sys.stderr)
        return 2
    try:
        with open(target, 'x') as handle:
            handle.write(json.dumps(mapping, indent=2) + '\n')
    except FileExistsError:
        print('Block map output appeared during the run; refusing to overwrite: ' + str(target),
              file=sys.stderr)
        return 2
    print('  wrote   : {}'.format(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
