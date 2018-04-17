from mock import patch
from buildercore import bakery
from . import base

class TestBuildercoreBakery(base.BaseCase):
    @patch('buildercore.utils.ymd')
    def test_ami_name(self, ymd):
        ymd.return_value = '2018-01-02'
        self.assertEqual(bakery.ami_name('dummy1--test'), 'dummy1.2018-01-02')
