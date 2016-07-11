from . import base
from mock import patch
import utils

class TestBuildercoreUtils(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_git_remote_branches(self):
        branches = utils.git_remote_branches('https://github.com/elifesciences/builder')
        self.assertIsInstance(branches, list)
        self.assertGreaterEqual(len(branches), 1)
        self.assertIn('master', branches)

    @patch('sys.stderr')
    def test_errcho(self, themock):
        self.assertEqual(
            'Hello, world',
            utils.errcho('Hello, world')
        )

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
            
