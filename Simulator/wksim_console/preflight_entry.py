"""WSL-only environment selection for the existing read-only preflight command."""
import os
from pathlib import Path
import sys

from Simulator.wksim_runtime.config import load_config


def main():
    path = Path(sys.argv[1]).resolve(strict=True)
    config = load_config(path)
    # Only source the reviewed local overlay, never a user-supplied setup script.
    # The real preflight still receives the requested config and reports mismatch.
    selected = load_config(Path(__file__).resolve().parents[1] /
        'wksim_runtime/examples' / (config['stack'] + '-mission.json'))
    script = '''set -eo pipefail
source "$1/ros-install/setup.bash"
if [[ -n $2 ]]; then source "$2/ros-install/local_setup.bash"; fi
source "$3/install/local_setup.bash"
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
exec python3 -B -m Simulator.wksim_runtime.preflight "$4"
'''
    os.execvp('bash', ['bash','-c',script,'wksim',selected['dds_workspace'],
        selected.get('ap_candidate',''),selected['prometheus_workspace'],str(path)])


if __name__ == '__main__':
    main()
