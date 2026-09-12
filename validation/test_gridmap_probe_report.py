"""Reject false success markers using the retained real map-only report."""
import copy
import json
from pathlib import Path
import pytest
from validation.gridmap_cloud_probe.run_isolated import verify_probe_result


def real_report():
    return json.loads((Path(__file__).parent / '39-gridmap-cloud-20260912/run-01/probe.json').read_text())


def test_real_report_is_complete():
    verify_probe_result(real_report())


def test_bare_success_marker_is_rejected():
    with pytest.raises((KeyError, ValueError)):
        verify_probe_result({'result': 'pass'})


@pytest.mark.parametrize('failure', ['missing_cloud', 'wrong_query', 'wrong_node', 'duplicate_point'])
def test_retained_report_mutations_cannot_pass(failure):
    report = copy.deepcopy(real_report())
    if failure == 'missing_cloud':
        report['gates']['cloud_xyz32_voxel_set'] = False
    elif failure == 'wrong_query':
        report['queries'][0]['actual'] = 1
    elif failure == 'wrong_node':
        report['node_name'] = '/unrelated'
    else:
        report['ros_inputs']['cloud']['duplicate_voxel_count'] = 1
    with pytest.raises(ValueError):
        verify_probe_result(report)
