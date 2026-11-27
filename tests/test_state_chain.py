import inspect
import unittest
from unittest.mock import Mock

from framework import state_chain
from framework.spec import digest
from test_shadow_runtime import ctx


def chain(*values):
    out = []
    for i, value in enumerate(values,1):
        out.append(dict(subject='fixture',slot='color',seq=i,recorded_at=i,
                        old=out[-1]['new'] if out else None,new=value,
                        previous_sha=digest(out[-1]) if out else '0'*64))
    return out


def head(rows):
    return dict(seq=len(rows),sha=digest(rows[-1]) if rows else '0'*64)


class StateChainTests(unittest.TestCase):
    def observe(self, rows, anchor, **kw):
        args = dict(subject='fixture',slot='color',context=ctx(),now=10,allowed=lambda *_:True,
                    checkpoint=lambda *_:anchor,events=lambda *_:iter(rows))
        return state_chain.project_state_chain(**dict(args,**kw))

    def test_empty_withdrawal_and_reassertion(self):
        self.assertEqual(self.observe([],head([])),{'status':'empty'})
        rows=chain('blue',None)
        self.assertEqual(self.observe(rows,head(rows)),dict(status='retired',seq=2,recorded_at=2))
        rows=chain('blue',None,'green')
        self.assertEqual(self.observe(rows,head(rows)),dict(status='active',value='green',seq=3,recorded_at=3))

    def test_authorization_and_budget_precede_data_access(self):
        checkpoint, events = Mock(), Mock()
        self.assertEqual(self.observe([],None,**dict(allowed=lambda *_:False,checkpoint=checkpoint,events=events)),
                         {'error':'NOT_FOUND_OR_DENIED'})
        checkpoint.assert_not_called()
        self.assertEqual(self.observe([],None,events=events),{'status':'unknown','reason':'NO_CHECKPOINT'})
        self.assertEqual(self.observe([],dict(seq=4097,sha='1'*64),events=events),{'status':'unknown','reason':'CHAIN_BUDGET'})
        events.assert_not_called()

    def test_truncation_disagreement_or_modified_tail_never_emits(self):
        rows=chain('blue','orange'); anchor=head(rows)
        for offered in (rows[:-1],list(reversed(rows)),[rows[0],dict(rows[1],old='wrong')],
                        [rows[0],dict(rows[1],new='wrong')], [rows[0],dict(rows[1],subject='other')],
                        [rows[0],dict(rows[1],recorded_at=11)]):
            self.assertEqual(self.observe(offered,anchor),{'error':'CHAIN_CONFLICT'})

    def test_pinned_head_digest_mutant_would_emit_changed_tail(self):
        lines=inspect.getsource(state_chain)
        guard=" or previous_sha != head['sha']"
        self.assertEqual(lines.count(guard),1)
        mutant={}; exec(compile(lines.replace(guard,'',1),'<chain-anchor-mutant>','exec'),mutant)
        rows=chain('blue'); changed=[dict(rows[0],new='changed')]; anchor=head(rows)
        self.assertEqual(self.observe(changed,anchor),{'error':'CHAIN_CONFLICT'})
        wrong=mutant['project_state_chain'](subject='fixture',slot='color',context=ctx(),now=10,
                     allowed=lambda *_:True,checkpoint=lambda *_:anchor,events=lambda *_:iter(changed))
        self.assertEqual(wrong['value'],'changed')
