import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from framework import state_lease
from shadow_runtime.state_event_port import StateEventStore
from shadow_runtime.state_view_port import file_state_view
from test_shadow_runtime import ctx


def args(**kw):
    return dict(dict(subject='fixture',slot='phase',context=ctx(),now=10,allowed=lambda *_:True),**kw)


class StateLeaseTests(unittest.TestCase):
    def test_expiry_boundary_and_mutation(self):
        unit = dict(status='active',value='ready',seq=1,recorded_at=10,checkpoint={'seq':1,'sha':'1'*64})
        self.assertEqual(state_lease.lease_view(unit,now=14,ttl_seconds=5)['status'],'stable')
        at = state_lease.lease_view(unit,now=15,ttl_seconds=5)
        self.assertEqual(at,dict(status='weak',value='ready',seq=1,recorded_at=10,age_seconds=5,ttl_seconds=5))
        source = inspect.getsource(state_lease); literal = 'age >= ttl_seconds'
        self.assertEqual(source.count(literal),1)
        altered = {}; exec(compile(source.replace(literal,'age > ttl_seconds',1),'<lease-boundary-mutant>','exec'),altered)
        self.assertEqual(altered['lease_view'](unit,now=15,ttl_seconds=5)['status'],'stable')
        self.assertEqual(state_lease.lease_view(unit,now=9,ttl_seconds=5),{'status':'unknown','reason':'INVALID_RECORDED_TIME'})
        with self.assertRaisesRegex(ValueError,'INVALID_LEASE_TIME'):
            state_lease.lease_view(unit,now=10,ttl_seconds=True)

    def test_denial_does_not_enter_storage_and_preserves_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateEventStore(tmp,synthetic=True)
            allowed = Mock(return_value=False)
            out = file_state_view(store,**args(allowed=allowed),ttl_seconds=5)
            self.assertEqual(out,{'error':'NOT_FOUND_OR_DENIED'})
            allowed.assert_called_once()
            self.assertFalse(store.root.exists())
        self.assertEqual(state_lease.lease_view({'status':'unknown','reason':'NO_CHECKPOINT'},now=10,ttl_seconds=5),
                         {'status':'unknown','reason':'NO_CHECKPOINT'})

    def test_reopen_expiry_withdrawal_and_corruption_do_not_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateEventStore(tmp,synthetic=True)
            def observe(now):
                return file_state_view(StateEventStore(tmp,synthetic=True),**args(now=now),ttl_seconds=5)
            self.assertEqual(observe(10),{'status':'empty'})
            head=store.inspect(**args())['checkpoint']
            first=store.append(**args(),expected=head,old=None,new='ready')['checkpoint']
            proof, = Path(store.root).glob('*.json'); before=proof.read_bytes()
            self.assertEqual(observe(15)['value'],'ready')
            self.assertEqual(observe(15)['status'],'weak')
            self.assertEqual(proof.read_bytes(),before)
            self.assertEqual(store.append(**args(now=16),expected=first,old='ready',new=None)['status'],'appended')
            self.assertEqual(observe(30),dict(status='retired',seq=2,recorded_at=16))
            proof.write_bytes(b'{')
            self.assertEqual(observe(30),{'error':'CHAIN_CONFLICT'})
            self.assertEqual(proof.read_bytes(),b'{')
