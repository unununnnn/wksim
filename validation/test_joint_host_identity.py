"""Historical process evidence must never query a reused PID after host restart."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_joint_product_lifecycle import recorded_host


class HostEvidenceTests(unittest.TestCase):
    def test_old_record_uses_contemporaneous_evidence_without_live_pid_queries(self):
        original=dict(pid=828,pgid=828,start_ticks=19268)
        record=dict(unowned_ap_before=original,unowned_ap_after=original)
        item=dict(process_identity=1000,remaining_group_members=[])
        with patch('audit_joint_product_lifecycle.group_members',side_effect=AssertionError('live PID query')):
            recorded_host(record,item)
        with self.assertRaises(ValueError): recorded_host(dict(record,unowned_ap_after=None),item)
        with self.assertRaises(ValueError): recorded_host(record,dict(item,remaining_group_members=[original]))

    def test_live_verification_requires_matching_boot_before_querying_group(self):
        record=dict(host_boot_id='11111111-2222-4333-8444-555555555555')
        item=dict(process_identity=1000,remaining_group_members=[])
        with patch('audit_joint_product_lifecycle.host_boot_id',return_value='other-host'),\
             patch('audit_joint_product_lifecycle.group_members',side_effect=AssertionError('reused PID query')):
            with self.assertRaisesRegex(ValueError,'same recorded boot'): recorded_host(record,item,current_host=True)
        with patch('audit_joint_product_lifecycle.host_boot_id',return_value=record['host_boot_id']),\
             patch('audit_joint_product_lifecycle.group_members',return_value=[]) as current:
            recorded_host(record,item,current_host=True)
            current.assert_called_once_with(1000)


if __name__=='__main__': unittest.main()
