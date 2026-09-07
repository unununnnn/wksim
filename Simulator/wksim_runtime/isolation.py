"""Cooperative Linux reservations; lock files persist to avoid inode replacement races."""
import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

_private_tmp = None


def isolate_temporary_files(consumer_sockets=()):
    """Private writable /tmp while retaining read access to pinned old builds.

    PX4's native daemon CLI uses /tmp/px4-sock-<instance>, which network/IPC
    namespaces alone do not isolate. Overlay writes/unlinks stay private; the
    existing lower tree is never modified. New build artifacts use a persistent
    project-owned directory so post-run evidence remains readable.
    """
    global _private_tmp
    check_isolation()
    consumers=sorted({str(Path(path).parent) for path in consumer_sockets})
    namespace=os.readlink('/proc/self/ns/mnt')
    if namespace==os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('Private mount namespace required before isolating /tmp')
    if _private_tmp is not None:
        if _private_tmp['mount_namespace']!=namespace or os.stat('/tmp').st_dev!=_private_tmp['device']:
            raise RuntimeError('Private temporary mount identity changed')
        if consumers and consumers!=[item['path'] for item in _private_tmp['consumer_directories']]:
            raise RuntimeError('Consumer directories must be selected before isolating temporary files')
        return dict(_private_tmp)
    directory=Path(tempfile.mkdtemp(prefix='wksim-private-tmp-',dir='/root'))
    for name in ('upper','work','artifacts'):
        (directory/name).mkdir(mode=0o700)
    before=os.stat('/tmp').st_dev
    command=['mount','-t','overlay','overlay','-o',
             f'lowerdir=/tmp,upperdir={directory}/upper,workdir={directory}/work','/tmp']
    shared=[]
    with ExitStack() as descriptors:
        # Pin only admitted view/telemetry directories before covering /tmp.
        # A late host receiver must use the same directory inode as physics;
        # an overlay-created directory would permanently hide that receiver.
        for name in consumers:
            path=Path(name)
            if path.parent!=Path('/tmp') or path.is_symlink() or path.resolve()!=path:
                raise RuntimeError('Consumer directory must be a direct private /tmp child')
            path.mkdir(mode=0o700,exist_ok=True)
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            descriptors.callback(os.close,fd)
            info=os.fstat(fd)
            if (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700
                    or (path.stat().st_dev,path.stat().st_ino)!=(info.st_dev,info.st_ino)):
                raise RuntimeError('Consumer directory ownership, mode or identity differs')
            shared.append(dict(path=name,device=info.st_dev,inode=info.st_ino,fd=fd))
        subprocess.run(command,check=True,capture_output=True,text=True)
        for item in shared:
            subprocess.run(['mount','--no-canonicalize','--bind',f"/proc/self/fd/{item['fd']}",item['path']],
                           pass_fds=(item['fd'],),check=True,capture_output=True,text=True)
            info=Path(item['path']).stat()
            if (info.st_dev,info.st_ino)!=(item['device'],item['inode']):
                raise RuntimeError('Consumer directory bind did not preserve the selected host inode')
            del item['fd']
    device=os.stat('/tmp').st_dev
    if device==before:
        raise RuntimeError('Temporary directory did not acquire a private filesystem')
    os.environ['TMPDIR']=str(directory/'artifacts')
    tempfile.tempdir=None
    _private_tmp=dict(root=str(directory),mount_namespace=namespace,device=device,lower_device=before,
                      artifact_directory=str(directory/'artifacts'),command=command,consumer_directories=shared)
    return dict(_private_tmp)


def resources(config, directory):
    ap = config['stack'] == 'arducopter'
    net = os.readlink('/proc/self/ns/net')
    ports = [('udp', p) for p in ((12019, 19002, 19003, 19004, 14660) if ap
                                 else (18888, 18591, 14661))]
    if not ap:
        ports.append(('tcp', 4581))
    return dict(experiment_kind='independent', run_id=config['run_id'],
                output=str(Path(directory).resolve()), network_namespace=net,
                ipc_namespace=os.readlink('/proc/self/ns/ipc'),
                shm_device=os.stat('/dev/shm').st_dev,
                vehicle_id=config['vehicle_id'], ros_domain=77,
                public_namespace='/uav1/prometheus',
                native_prefix='/ap' if ap else '/wksim_px4_21',
                native_system_id=241 if ap else 22,
                xrce_client_key=0xAAAABBBB if ap else 22,
                ports=[dict(protocol=kind, port=port) for kind, port in ports],
                display_socket=str(Path(config['display_socket']).resolve()) if config.get('display_socket') else None,
                telemetry_socket=str(Path(config['telemetry_socket']).resolve()) if config.get('telemetry_socket') else None,
                independent_clock=True, dds_transport='private network and private /dev/shm')


def keys(resource):
    scope = resource['network_namespace']
    result = [('run_id', resource['run_id']), ('output', resource['output'])]
    if resource.get('experiment_kind')=='joint':
        # Every joint epoch creates a fresh private network/IPC namespace.
        # The manager reserves the public run/output identity across epochs.
        if resource.get('display_socket'): result.append(('display_socket',resource['display_socket']))
        return result
    if resource['display_socket']:
        result.append(('display_socket', resource['display_socket']))
        path = Path(resource['display_socket'])
        if path.exists():
            info = path.stat()
            result.append(('display_inode', info.st_dev, info.st_ino))
    # Share the existing consumer key space: a telemetry destination must also
    # conflict with another experiment's display destination, including aliases.
    if resource.get('telemetry_socket'):
        result.append(('display_socket', resource['telemetry_socket']))
        path = Path(resource['telemetry_socket'])
        if path.exists():
            info = path.stat()
            result.append(('display_inode', info.st_dev, info.st_ino))
    for field in ('vehicle_id', 'ros_domain', 'public_namespace', 'native_prefix',
                  'native_system_id', 'xrce_client_key'):
        result.append((scope, field, resource[field]))
    result.extend((scope, p['protocol'], p['port']) for p in resource['ports'])
    return result


class Reservation:
    def __init__(self, resource, root='/run/wksim-reservations'):
        self.resource, self.root, self.fds = resource, Path(root), []

    def __enter__(self):
        import fcntl
        self.root.mkdir(mode=0o700, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise RuntimeError('Unsafe reservation directory')
        try:
            for key in sorted(keys(self.resource), key=repr):
                encoded = json.dumps(key).encode()
                path = self.root / (hashlib.sha256(encoded).hexdigest() + '.lock')
                fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                self.fds.append(fd)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError('Independent experiment resource conflict: ' + repr(key)) from error
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *unused):
        for fd in self.fds:
            os.close(fd)
        self.fds.clear()


def check_isolation():
    for kind in ('net', 'ipc'):
        if os.readlink('/proc/self/ns/' + kind) == os.readlink('/proc/1/ns/' + kind):
            raise RuntimeError('Use run-wksim.sh: private Linux network and IPC namespaces required')
    if os.stat('/dev/shm').st_dev == os.stat('/proc/1/root/dev/shm').st_dev:
        raise RuntimeError('Use run-wksim.sh: private /dev/shm required for Fast DDS')
