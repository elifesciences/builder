from . import base
from unittest.mock import patch, call
import utils

class TestUtils(base.BaseCase):
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
    def test_errcho(self, stderr):
        self.assertEqual(
            'Hello, world',
            utils.errcho('Hello, world')
        )
        self.assertEqual(
            [call('Hello, world'), call('\n')],
            stderr.write.call_args_list
        )
        stderr.flush.assert_called_with()

    def test_rmval(self):
        expected_list = [
            ([1, 2, 3], [2], ([1, 3], [2])),
            (['a', 'b', 'c'], ['b'], (['a', 'c'], ['b'])),
            (['a', 'b', 'c'], ['c', 'a'], (['b'], ['c', 'a'])),

            ([1, 2, 3], ['a'], ([1, 2, 3], [])),
            ([1, 2, 3], [], ([1, 2, 3], [])),
            ([], [1, 2, 3], ([], [])),
        ]
        for data, tbr, expected in expected_list:
            self.assertEqual(utils.rmval(data, *tbr), expected)

    @patch('utils.get_input', return_value='1')
    def test_pick(self, get_input):
        value = utils._pick('project', ['lax', 'bot'], '/tmp/cache')
        self.assertEqual('lax', value)

    @patch('utils.get_input', return_value='lax')
    def test_uin(self, get_input):
        value = utils.uin('project')
        self.assertEqual('lax', value)

    @patch('utils.get_input', return_value='')
    def test_uin_default(self, get_input):
        value = utils.uin('project', default='lax')
        self.assertEqual('lax', value)

    def test_mkdirp_is_idempotent_on_existing_directories(self):
        utils.mkdirp(".")

    def test_pwd(self):
        self.assertRegex(utils.pwd(), "^/.*/src$")

    def test_table(self):
        class AnObject():
            def __init__(self, project, instance_id):
                self.project = project
                self.instance_id = instance_id

        rows = [AnObject('lax', 'ci'), AnObject('bot', 'end2end')]
        keys = ['project', 'instance_id']
        self.assertEqual("lax, ci\nbot, end2end", utils.table(rows, keys))

    def test_strtobool(self):
        true_case_list = [
            True,
            1, "1",
            "y", "yes", "Yes", "YES",
            "t", "true", "True", "TRUE",
        ]
        for true_case in true_case_list:
            self.assertEqual(True, utils.strtobool(true_case))

        false_case_list = [
            False,
            0, "0",
            "n", "no", "No", "NO",
            "f", "false", "False", "FALSE"
        ]
        for false_case in false_case_list:
            self.assertEqual(False, utils.strtobool(false_case))

        self.assertRaises(ValueError, utils.strtobool, "this value is neither true nor false")
