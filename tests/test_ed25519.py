"""RFC 8032 test vector: proves the stdlib Ed25519 interoperates with other implementations."""
import binascii
import unittest

import scripts.ed25519 as ed25519

SEED = binascii.unhexlify('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC = binascii.unhexlify('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
SIGNATURE = binascii.unhexlify('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')


class Ed25519VectorTests(unittest.TestCase):
    def test_public_key_matches_rfc8032_vector(self):
        self.assertEqual(ed25519.public_key(SEED), PUBLIC)

    def test_signature_matches_rfc8032_vector(self):
        self.assertEqual(ed25519.sign(SEED, b''), SIGNATURE)

    def test_vector_signature_verifies(self):
        self.assertTrue(ed25519.verify(PUBLIC, b'', SIGNATURE))

    def test_tampered_message_is_rejected(self):
        self.assertFalse(ed25519.verify(PUBLIC, b'x', SIGNATURE))

    def test_tampered_signature_is_rejected(self):
        self.assertFalse(ed25519.verify(PUBLIC, b'', SIGNATURE[:-1] + bytes([SIGNATURE[-1] ^ 1])))

    def test_other_public_key_is_rejected(self):
        other = bytes([PUBLIC[0] ^ 1]) + PUBLIC[1:]
        self.assertFalse(ed25519.verify(other, b'', SIGNATURE))


if __name__ == '__main__':
    unittest.main()