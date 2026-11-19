import dataclasses
import multiprocessing
import pathlib
import tempfile
import unittest
from shadow_runtime.writer_status import WriterStatus


def _worker(root, handle, state, start):
    instance = WriterStatus(root, synthetic=True)
    start.wait(timeout=15)
    for i in range(10):
        instance.publish(handle, state=state, now=10+i)


class WriterStatusTests(unittest.TestCase):
    def test_spawned_writers_on_shared_root_remain_distinguishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = WriterStatus(tmp, synthetic=True)
            ctx = multiprocessing.get_context('spawn')
            gate = ctx.Barrier(2)
            workers = []
            expected = {'dsh-1':'healthy','zcode-1':'degraded'}
            try:
                for name,state in expected.items():
                    proc = ctx.Process(target=_worker,args=(tmp,s.enroll(name),state,gate))
                    proc.start(); workers.append(proc)
                for proc in workers:
                    proc.join(25); self.assertEqual(proc.exitcode,0)
            finally:
                for proc in workers:
                    if proc.is_alive(): proc.terminate()
                    proc.join(5); proc.close()
            reader = WriterStatus(tmp, synthetic=True)
            for name,state in expected.items():
                self.assertEqual(reader.read(name,now=20),dict(writer_id=name,seq=10,observed=19,state=state))
            self.assertEqual(reader.read('third',now=20),{'state':'unknown'})

    def test_freshness_ownership_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=WriterStatus(tmp,synthetic=True); a=s.enroll('a'); b=s.enroll('b')
            self.assertEqual(s.read('a',now=0),{'state':'unknown'})
            with self.assertRaises(ValueError): s.enroll('a')
            with self.assertRaises(ValueError): s.publish(dataclasses.replace(a,writer_id='b'),state='healthy',now=1)
            self.assertEqual(s.publish(b,state='degraded',now=10),{'writer_id':'b','seq':1})
            with self.assertRaises(ValueError): s.publish(b,state='healthy',now=9)
            self.assertEqual(s.read('b',now=69)['state'],'degraded')
            for tick in (9,70): self.assertEqual(s.read('b',now=tick),{'state':'unknown'})
            self.assertEqual(s.read(None,now=10),{'state':'unknown'})
            s._path('a').write_bytes(s._path('b').read_bytes())
            self.assertEqual(s.read('a',now=11),{'state':'unknown'})
            self.assertEqual(s.read('b',now=11)['seq'],1)
            with self.assertRaises(ValueError): s.publish(a,state='healthy',now=11)
            s._path('b').write_text('{',encoding='utf-8')
            self.assertEqual(s.read('b',now=11),{'state':'unknown'})

    def test_requires_synthetic_and_nonempty_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): WriterStatus(tmp,synthetic=1)
            s=WriterStatus(tmp,synthetic=True)
            for name in (None,'','A/B','..'):
                with self.assertRaises(ValueError): s.enroll(name)
            self.assertEqual(list(pathlib.Path(tmp).iterdir()),[])
