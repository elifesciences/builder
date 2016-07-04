from . import base
import utils

class TestBuildercoreUtils(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_rmval(self):
        expected_list = [
            ([1,2,3], [2], ([1,3], [2])),
            (['a','b','c'], ['b'], (['a','c'], ['b'])),
            (['a','b','c'], ['c', 'a'], (['b'], ['c', 'a'])),
            
            ([1,2,3], ['a'], ([1,2,3], [])),
            ([1,2,3], [], ([1,2,3], [])),
            ([], [1,2,3], ([], [])),
        ]
        for data, tbr, expected in expected_list:
            self.assertEqual(utils.rmval(data, *tbr), expected)
            
