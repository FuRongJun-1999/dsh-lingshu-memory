import tempfile
from pathlib import Path
import unittest
from scripts.spec_tree import compare


class SpecTreeTests(unittest.TestCase):
    def test_change_add_remove_reported_separately_without_refreezing(self):
        # Independent known SHA-256 of the three bytes abc.
        digest = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
        lock = dict(format=1,algorithm='sha256-bytes',reason='fixture',files={'nested/spec.json':digest})
        clean = dict(added=[],missing=[],changed=[])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'nested').mkdir(); p=root/'nested/spec.json'; p.write_bytes(b'abc')
            self.assertEqual(compare(root, lock),clean)
            p.write_bytes(b'abc\n'); self.assertEqual(compare(root,lock),dict(clean,changed=['nested/spec.json']))
            p.write_bytes(b'abc'); new=root/'extra.txt'; new.write_bytes(b'abc')
            self.assertEqual(compare(root,lock),dict(clean,added=['extra.txt']))
            p.unlink(); self.assertEqual(compare(root,lock),dict(clean,added=['extra.txt'],missing=['nested/spec.json']))
            p.write_bytes(b'abc'); new.unlink(); self.assertEqual(compare(root,lock),clean)
        self.assertEqual(lock['files'],{'nested/spec.json':digest})
