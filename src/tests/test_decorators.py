from unittest.mock import patch

import decorators

from . import base


class TestDecorators(base.BaseCase):
    @patch('decorators.LOG.info')
    def test_timeit_smoke_test(self, info):
        @decorators.timeit
        def some_task(param, **kwargs):
            pass
        some_task(42, option='value')
        (args, _) = info.call_args
        self.assertIsInstance(args[0], str)
        self.assertEqual(args[1], 'some_task')
        self.assertEqual(args[2], (42,))
        self.assertEqual(args[3], {'option': 'value'})
        self.assertIsInstance(args[4], float)
        self.assertGreater(args[4], 0.0)

    def test_deffile(self):
        self.assertEqual('/tmp/template.json', decorators.deffile('template.json'))

    def test_setdefault(self):
        decorators.setdefault('.active-stack', 'lax--ci')
        with open('/tmp/.active-stack') as f:
            self.assertEqual(f.read(), 'lax--ci')

    @patch('buildercore.core.active_stack_names', return_value=['dummy1--ci'])
    @patch('utils.get_input', return_value='1')
    def test_requires_aws_project_stack(self, get_input, active_stack_names):
        @decorators.requires_aws_project_stack('dummy1')
        def some_task(stackname):
            self.assertEqual('dummy1--ci', stackname)
            return 'result'

        self.assertEqual(some_task('dummy1--ci'), 'result')

    @patch('buildercore.core.active_stack_names', return_value=['dummy1--ci', 'dummy1--end2end'])
    @patch('utils.get_input', return_value='2')
    def test_requires_aws_stack(self, get_input, active_stack_names):
        @decorators.requires_aws_stack
        def some_task(stackname):
            self.assertEqual('dummy1--end2end', stackname)
            return 'result'

        self.assertEqual(some_task('dummy1--end2end'), 'result')
