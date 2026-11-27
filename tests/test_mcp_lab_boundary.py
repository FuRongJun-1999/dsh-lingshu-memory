import unittest
from unittest.mock import Mock
from shadow_runtime.mcp_lab import Session, TOOL


class McpBoundaryTests(unittest.TestCase):
    def session(self, who):
        store = Mock()
        store.execute.return_value = {"fixture": True}
        session = Session(store, who)
        def rpc(method, params=None, notification=False):
            msg = dict(jsonrpc='2.0',method=method,params=params or {})
            if not notification:
                msg['id'] = 7
            return session.dispatch(msg)
        return store, rpc

    def ready(self, rpc):
        self.assertEqual(rpc('initialize',{'protocolVersion':'2024-11-05'})['result']['protocolVersion'],'2024-11-05')
        self.assertIsNone(rpc('notifications/initialized',notification=True))

    def test_early_and_notification_calls_have_no_effect(self):
        store,rpc=self.session('alice')
        params=dict(name=TOOL,arguments={'request':{'kind':'Read.get'}})
        self.assertEqual(rpc('tools/call',params)['error']['code'],-32600)
        self.ready(rpc)
        self.assertIsNone(rpc('tools/call',params,notification=True))
        store.execute.assert_not_called()

    def test_identity_and_operation_fail_before_store(self):
        store,rpc=self.session('bob')
        self.ready(rpc)
        self.assertEqual(rpc('tools/call',dict(name=TOOL,arguments={'request':{'kind':'Read.get'},'principal':'alice'}))['error']['code'],-32602)
        for request in ({'kind':'Write.create','durability_request':'process'},{'kind':'Govern.restore'},{'kind':'Read.search'}):
            self.assertTrue(rpc('tools/call',dict(name=TOOL,arguments={'request':request}))['result']['isError'])
        store.execute.assert_not_called()
        rpc('tools/call',dict(name=TOOL,arguments={'request':{'kind':'Read.get'}}))
        self.assertEqual(store.execute.call_args.args[1]['principal'],'bob')
