"""Copy pinned generated launch files once into the independent PX4 resource.

The source is a retained build reference, never a runtime link. Existing files
are verified rather than overwritten; module links only target local ./px4.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

PIN='987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(source, root):
    if root != root.resolve() or root != Path('/root/wksim-dependencies/px4-d6f12ad1'):
        raise ValueError('Requires the explicit real project-owned PX4 directory')
    target=root/'build/px4_sitl_default/bin'
    if target.resolve()!=target or sha(source/'px4')!=PIN or sha(target/'px4')!=PIN:
        raise ValueError('Source/independent target firmware identity differs')
    result=dict(source_reference=str(source),independent_root=str(root),binary_sha256=PIN,files={})
    for path in sorted(source.iterdir()):
        if path.name=='px4': continue
        if path.name=='px4-alias.sh' and path.is_file() and not path.is_symlink():
            destination=target/path.name
            if destination.exists():
                if destination.is_symlink() or sha(destination)!=sha(path):
                    raise ValueError('Existing project launch file differs; not overwriting')
            else:
                shutil.copy2(path,destination)
            result['files'][path.name]=dict(sha256=sha(destination))
        elif path.is_symlink() and path.name.startswith('px4-') and os.readlink(path)=='px4':
            destination=target/path.name
            if destination.exists() or destination.is_symlink():
                if not destination.is_symlink() or os.readlink(destination)!='px4':
                    raise ValueError('Existing module entry differs; not overwriting')
            else:
                destination.symlink_to('px4')
            if destination.resolve()!=target/'px4':
                raise ValueError('Module entry escapes independent binary directory')
            result['files'][path.name]=dict(relative_link='px4')
        else:
            raise ValueError('Unexpected reference build/bin entry: '+str(path))
    if 'px4-alias.sh' not in result['files'] or 'px4-commander' not in result['files']:
        raise ValueError('Missing required launch entries')
    result['status']='pass'
    (root/'wksim-runtime-files.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-bin',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    args=p.parse_args()
    result=restore(args.source_bin,args.root)
    print(json.dumps(result,indent=2))
