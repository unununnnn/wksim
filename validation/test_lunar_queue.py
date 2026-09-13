"""Offline selection contract: live states/triage/dependencies decide dispatch."""
import unittest
from tools.lunar_queue import candidates


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.plan={'children':[dict(key='one',priority=1,tier='luna',prerequisite_keys=[],blocking_issue_numbers=[]),
            dict(key='two',priority=2,tier='luna',prerequisite_keys=['one'],blocking_issue_numbers=[7]),
            dict(key='expert',priority=0,tier='astra',prerequisite_keys=[],blocking_issue_numbers=[])]}
        self.issued={k:{'number':n} for k,n in [('one',50),('two',51),('expert',52)]}
        self.states={n:dict(state='OPEN',labels=[{'name':'ready-for-agent'}]) for n in (50,51,52,7)}
    def test_only_one_front_is_ready(self):
        ready,_=candidates(self.plan,self.issued,self.states,'luna')
        self.assertEqual([r['key'] for r,_ in ready],['one'])
    def test_both_local_and_parent_prerequisites_required(self):
        self.states[50]['state']='CLOSED'
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0],[])
        self.states[7]['state']='CLOSED'
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0][0][0]['key'],'two')
    def test_failed_triage_ticket_not_repeated(self):
        self.states[50]['labels']=[{'name':'needs-triage'}]
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0],[])
    def test_missing_live_or_registry_is_not_ready(self):
        del self.states[50]
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0],[])
        self.issued.pop('two')
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0],[])
    def test_missing_dependency_registry_is_blocked(self):
        self.issued.pop('one')
        self.states[7]['state']='CLOSED'
        self.assertEqual(candidates(self.plan,self.issued,self.states,'luna')[0],[])
    def test_decision_uses_human_label_only_when_explicitly_selected(self):
        self.plan['children'][2]['tier']='decision'
        self.states[52]['labels']=[{'name':'ready-for-human'}]
        ready,_=candidates(self.plan,self.issued,self.states,'decision')
        self.assertEqual(ready[0][0]['key'],'expert')
        ready,_=candidates(self.plan,self.issued,self.states,'luna')
        self.assertEqual([x[0]['key'] for x in ready],['one'])


if __name__=='__main__':unittest.main()
