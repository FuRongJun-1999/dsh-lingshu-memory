import inspect
import tempfile
import unittest
from unittest.mock import patch

from framework import task_progress
from shadow_runtime.state_event_port import EMPTY, StateEventStore
from shadow_runtime.task_progress_port import SLOT, change_task_progress
from test_shadow_runtime import ctx


def scope(**kw):
    return dict(dict(context=ctx(),now=10,allowed=lambda *_:True),**kw)


class TaskProgressTests(unittest.TestCase):
    def test_done_requires_result_and_terminal_cannot_reopen(self):
        d=task_progress.decide_task_progress
        active=d(None,target='active')
        with self.assertRaisesRegex(ValueError,'TASK_RESULT_REQUIRED'):
            d(active,target='done',result=' ')
        completed=d(active,target='done',result='fixture complete')
        self.assertEqual(completed,dict(status='done',result='fixture complete'))
        self.assertEqual(d(completed,target='active'),{'error':'TASK_TRANSITION_REJECTED'})
        self.assertEqual(d({'status':'unknown','result':None},target='active'),{'error':'TASK_STATE_UNKNOWN'})
        text=inspect.getsource(task_progress); anchor="'done': set()"
        self.assertEqual(text.count(anchor),1)
        mutant={}; exec(compile(text.replace(anchor,"'done': {'active'}",1),'<task-terminal-mutant>','exec'),mutant)
        self.assertEqual(mutant['decide_task_progress'](completed,target='active')['status'],'active')

    def test_file_path_reopen_checks_grant_and_stale_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=StateEventStore(tmp,synthetic=True)
            def change(target, head, result=None, **kw):
                return change_task_progress(StateEventStore(tmp,synthetic=True), task_id='fixture',target=target,
                                            result=result,expected=head,**scope(**kw))
            self.assertEqual(change('active',EMPTY,allowed=lambda *_:False),{'error':'NOT_FOUND_OR_DENIED'})
            self.assertFalse(store.root.exists())
            first=change('active',EMPTY)['checkpoint']
            self.assertEqual(change('blocked',EMPTY),{'error':'STATE_CHANGED'})
            second=change('blocked',first)['checkpoint']
            resumed=change('active',second)['checkpoint']
            done=change('done',resumed,'fixture complete')
            self.assertEqual(done['task']['status'],'done')
            self.assertEqual(change('active',done['checkpoint']),{'error':'TASK_TRANSITION_REJECTED'})
            self.assertEqual(store.inspect(subject='fixture',slot=SLOT,**scope())['seq'],4)

    def test_change_between_read_and_append_never_returns_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=StateEventStore(tmp,synthetic=True); real=StateEventStore.append
            def race(target,**request):
                self.assertEqual(real(target,**dict(request,new='{"result":null,"status":"active"}'))['status'],'appended')
                return real(target,**request)
            with patch.object(StateEventStore,'append',race):
                got=change_task_progress(store,task_id='fixture',target='active',result=None,expected=EMPTY,**scope())
            self.assertEqual(got,{'error':'STATE_CHANGED'})
            self.assertEqual(store.inspect(subject='fixture',slot=SLOT,**scope())['seq'],1)
