from buildercore import bvars
from . import base
class One(base.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_encode(self):
        "returns an json serialised, ascii encoded, base64 representation of it's input"
        self.assertEqual('ImZvbyI=', bvars.encode_bvars('foo'))

    def test_decode(self):
        self.assertEqual('foo', bvars.decode_bvars('ImZvbyI='))
