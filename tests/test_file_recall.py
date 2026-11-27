import tempfile
import unittest

from sandbox_runtime.controller import AlertSink, Controller, RecallPorts
from sandbox_runtime.store import Probe
from shadow_runtime.recall_port import FileRecallPort, recall_file
from shadow_runtime.store import ShadowMarkdownStore
from test_shadow_runtime import Q, cspace, ctx, write_req
from test_sandbox_controller import task


def record(token, body='blue widget limit 8', readers=('alice','bob')):
    req = write_req(token, body, readers=readers)
    req['condition_space']['attributes'] = [dict(key=k,value=v) for k,v in (
        ('memory.architecture','widget'), ('memory.key','widget.limit'), ('memory.version','v1'), ('region','east'))]
    return req


def run(store, value, who='alice'):
    return recall_file(store, value, context_provider=lambda:ctx(who), clock=lambda:10,
                       condition_query=cspace(), time_axis='effective', time_point=Q)


class FileRecallTests(unittest.TestCase):
    def test_text_miss_key_recovery_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(saved.execute(record('one', readers=('alice',)),ctx(),1)['outcome'],'ok')
            store = ShadowMarkdownStore(tmp, synthetic=True)
            ready = run(store,task(query='unrelated'))
            self.assertEqual([x['operation'] for x in ready['actions']],['search','search','get','get'])
            self.assertEqual(ready['output']['status'],'ready')
            self.assertEqual(ready['output']['records'][0]['body'],'blue widget limit 8')
            denied = run(store,task(),who='bob')
            self.assertEqual(denied['output'],dict(status='blocked',reason='EVIDENCE_GAP'))
            self.assertTrue(all(x['returned']==0 for x in denied['actions']))
            for budget, calls in [(dict(calls=0,bytes=0,retries=1),0),(dict(calls=64,bytes=0,retries=1),2)]:
                blocked = run(store,task(budget=budget))
                self.assertEqual(blocked['output'],dict(status='blocked',reason='BUDGET'))
                self.assertEqual(len(blocked['actions']),calls)

    def test_manifest_change_between_prepare_and_emit_blocks(self):
        for action in ('Govern.change_policy', 'Write.modify'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                store = ShadowMarkdownStore(tmp, synthetic=True)
                self.assertEqual(store.execute(record('one'),ctx(),1)['outcome'],'ok')
                probe = Probe()
                port = FileRecallPort(store,probe,condition_query=cspace(),time_axis='effective',time_point=Q)
                ctrl = Controller(RecallPorts(port.search,port.get,probe),probe,context_provider=lambda:ctx('bob'),
                                  clock=lambda:10,alerts=AlertSink())
                t = task(); ticket = ctrl.prepare(t)
                self.assertEqual(len(probe.events),4)
                if action == 'Govern.change_policy':
                    req = dict(kind=action, node_id='node-1', expected_revision=1, caller_token='restrict',
                               reason='fixture', declared_sensitivity=1, reader_ceiling=['alice'])
                else:
                    req = dict(record('replace','blue widget limit 9'),kind=action,node_id='node-1',expected_revision=1)
                self.assertEqual(store.execute(req,ctx(),11)['outcome'],'ok')
                self.assertEqual(ctrl.emit(ticket,t),dict(status='blocked',reason='CONTEXT_CHANGED'))
                self.assertEqual(len(probe.events),4)

    def test_key_group_conflict_cannot_emit_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShadowMarkdownStore(tmp, synthetic=True)
            for key, body in [('a','blue widget'),('b','other evidence')]:
                self.assertEqual(store.execute(record(key,body),ctx(),1)['outcome'],'ok')
            self.assertEqual(run(store,task())['output'],dict(status='blocked',reason='AMBIGUOUS'))

    def test_terminal_check_after_last_read_drops_obsolete_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShadowMarkdownStore(tmp, synthetic=True)
            self.assertEqual(store.execute(record('one'),ctx(),1)['outcome'],'ok')
            probe, alerts = Probe(), AlertSink()
            port = FileRecallPort(store,probe,condition_query=cspace(),time_axis='effective',time_point=Q)
            def clock():
                if len(probe.events) == 5:
                    req = dict(kind='Govern.change_policy',node_id='node-1',expected_revision=1,caller_token='late',
                               reason='fixture',declared_sensitivity=1,reader_ceiling=['alice'])
                    self.assertEqual(store.execute(req,ctx(),11)['outcome'],'ok')
                return 10
            ctrl = Controller(RecallPorts(port.search,port.get,probe,port.validate),probe,
                              context_provider=lambda:ctx('bob'),clock=clock,alerts=alerts)
            self.assertEqual(ctrl.run(task()),dict(status='blocked',reason='CONTEXT_CHANGED'))
            self.assertEqual(len(probe.events),5)
            self.assertEqual(alerts.events,[dict(event='alert',reason='CONTEXT_CHANGED')])
