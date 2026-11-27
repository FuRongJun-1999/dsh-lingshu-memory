import inspect
import unittest
from unittest.mock import Mock

from framework import recent_window as module
from test_shadow_runtime import ctx


def options(**changes):
    return dict(dict(session='fixture',roles=frozenset({'user'}),limit=1,expected_generation=4,
                     context=ctx(),now=10,allowed=lambda *_:True,snapshot=lambda *_:None),**changes)


def row(seq, role='user', session='fixture'):
    return dict(session=session,seq=seq,role=role,text=str(seq))


class RecentWindowTests(unittest.TestCase):
    def test_filter_before_limit_and_newest_first(self):
        frame=dict(generation=4,events=(row(3),row(7),row(9,'assistant')))
        run=lambda limit:module.recent_window(**options(snapshot=lambda *_:frame,limit=limit))['events']
        self.assertEqual(run(1),[dict(seq=7,role='user',text='7',trust='untrusted_event')])
        self.assertEqual([x['seq'] for x in run(2)],[7,3])

    def test_denial_does_not_read_and_mixed_rows_fail_closed(self):
        port=Mock()
        self.assertEqual(module.recent_window(**options(allowed=lambda *_:False,snapshot=port)),{'error':'NOT_FOUND_OR_DENIED'})
        self.assertEqual(module.recent_window(**options(now=1000,snapshot=port)),{'error':'AUTH_REQUIRED'})
        port.assert_not_called()
        for rows in ((row(1),row(2,session='foreign')),(row(1),row(1)),tuple(row(i) for i in range(1,258))):
            self.assertEqual(module.recent_window(**options(snapshot=lambda *_:dict(generation=4,events=rows))),
                             {'error':'WINDOW_INVALID'})

    def test_stale_frame_and_generation_guard_mutation(self):
        kw=options(snapshot=lambda *_:dict(generation=5,events=(row(1),)))
        self.assertEqual(module.recent_window(**kw),{'error':'WINDOW_CHANGED'})
        source=inspect.getsource(module); guard="if frame['generation'] != expected_generation:"
        self.assertEqual(source.count(guard),1)
        changed={};exec(compile(source.replace(guard,'if False:',1),'<recent-generation-mutant>','exec'),changed)
        self.assertEqual(changed['recent_window'](**kw)['events'][0]['text'],'1')
