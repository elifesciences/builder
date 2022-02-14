import pytest
from functools import partial
import json
from os.path import join
from . import base
from buildercore import core, utils, project
from unittest import skip
from unittest.mock import patch, Mock
import botocore

class SimpleCases(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_hostname_struct_no_subdomain(self):
        expected = {
            'domain': "example.org",
            'int_domain': "example.internal",
            'subdomain': None,
            'project_hostname': None,
            'int_project_hostname': None,
            'hostname': None,
            'full_hostname': None,
            'int_full_hostname': None,
        }
        stackname = 'dummy1--test'
        self.assertEqual(core.hostname_struct(stackname), expected)

    def test_hostname_struct_with_subdomain(self):
        expected = {
            'domain': "example.org",
            'int_domain': "example.internal",
            'subdomain': 'dummy2',
            'hostname': 'ci--dummy2',
            'project_hostname': 'dummy2.example.org',
            'int_project_hostname': 'dummy2.example.internal',
            'full_hostname': 'ci--dummy2.example.org',
            'int_full_hostname': 'ci--dummy2.example.internal',
            'ext_node_hostname': 'ci--dummy2--%s.example.org',
            'int_node_hostname': 'ci--dummy2--%s.example.internal',
        }
        stackname = 'dummy2--ci'
        self.assertEqual(core.hostname_struct(stackname), expected)

    def test_project_name_from_stackname(self):
        expected = [
            ('elife-bot--2015-04-29', 'elife-bot'),
            ('elife-bot--2015-05-11v2', 'elife-bot'),
            ('elife-bot--large-gnott-again-2015-12-13', 'elife-bot'),
            ('elife-dashboard--2016-01-26', 'elife-dashboard'),
            ('elife-lax--2015-10-15-develop', 'elife-lax'),
            ('elife-metrics--2015-09-25', 'elife-metrics'),
            ('elife-metrics--prod-candidate', 'elife-metrics'),
            ('master-server--2014-12-24', 'master-server'),
        ]
        self.assertAllPairsEqual(core.project_name_from_stackname, expected)

    def test_parse_stackname(self):
        # basic
        expected = [
            ('lax--prod', ['lax', 'prod']),
            ('lax--prod--1', ['lax', 'prod--1']), # is this really what we're expecting?
            ('journal-cms--end2end', ['journal-cms', 'end2end']),
            ('journal-cms--end2end--2', ['journal-cms', 'end2end--2']), # again, really?
        ]
        self.assertAllPairsEqual(core.parse_stackname, expected)

        # extended
        expected = [
            ('lax--prod', ['lax', 'prod']),
            ('lax--prod--1', ['lax', 'prod', '1']),
            ('journal-cms--end2end', ['journal-cms', 'end2end']),
            ('journal-cms--end2end--2', ['journal-cms', 'end2end', '2']),
        ]
        self.assertAllPairsEqual(partial(core.parse_stackname, all_bits=True), expected)

        # as dict
        expected = [
            ('lax--prod', {"project_name": 'lax', "instance_id": 'prod'}),
            ('lax--prod--1', {"project_name": 'lax', "instance_id": 'prod', "cluster_id": '1'}),
            ('journal-cms--end2end', {"project_name": 'journal-cms', "instance_id": 'end2end'}),
            ('journal-cms--end2end--2', {"project_name": 'journal-cms', "instance_id": 'end2end', "cluster_id": '2'}),
        ]
        self.assertAllPairsEqual(partial(core.parse_stackname, all_bits=True, idx=True), expected)

    def test_master_server_stackname(self):
        self.assertTrue(core.is_master_server_stack('master-server--temp'))
        self.assertFalse(core.is_master_server_stack('master-some-project--end2end'))
        self.assertFalse(core.is_master_server_stack('lax--end2end'))

    def test_bad_pname_from_stackname(self):
        expected_error = [
            # project names by themselves. a stackname must be projectname + instance_id
            'elife-lax',
            # master server isn't special here
            'master-server',
            'asdf', # project name that doesn't exist
            # just bad values
            '', None, -1,
        ]
        for expected in expected_error:
            self.assertRaises(ValueError, core.project_name_from_stackname, expected)

    def test_master_server_identified(self):
        true_cases = [
            'master-server--master',
            'master-server--2016-01-01',
            'master-server--master--ci',
        ]
        results = list(map(core.is_master_server_stack, true_cases))
        self.assertTrue(all(results), "not all master servers identified: %r" % list(zip(true_cases, results)))

    def test_master_server_identified_false_cases(self):
        false_cases = [
            'master-server', # *stack* names not project names
            '', None, 123, {}, [], self
        ]
        results = list(map(core.is_master_server_stack, false_cases))
        self.assertFalse(all(results), "not all false cases identified: %r" % list(zip(false_cases, results)))

    def test_find_region(self):
        self.assertEqual(core.find_region(), "us-east-1")

    def test_find_region_when_more_than_one_is_available(self):
        try:
            base.switch_in_test_settings([
                'src/tests/fixtures/projects/dummy-project.yaml',
                'src/tests/fixtures/additional-projects/dummy-project-eu.yaml',
            ])
            core.find_region()
            self.fail("Shouldn't be able to choose a region")
        except core.MultipleRegionsError as e:
            self.assertCountEqual(["us-east-1", "eu-central-1"], e.regions())
        finally:
            base.switch_out_test_settings()

    def test_find_ec2_instances(self):
        self.assertEqual([], core.find_ec2_instances('dummy1--prod', allow_empty=True))

    def test_find_ec2_instances_requiring_a_non_empty_list(self):
        self.assertRaises(core.NoRunningInstances, core.find_ec2_instances, 'dummy1--prod', allow_empty=False)

    def test_all_sns_subscriptions_filters_correctly(self):
        cases = [
            ('lax--prod', []), # lax doesn't subscribe to anything
            ('observer--prod', ['bus-articles--prod', 'bus-metrics--prod']),
        ]
        fixture = json.load(open(join(self.fixtures_dir, 'sns_subscriptions.json'), 'r'))
        with patch('buildercore.core._all_sns_subscriptions', return_value=fixture):
            for stackname, expected_subs in cases:
                res = core.all_sns_subscriptions('someregion', stackname)
                actual_subs = [sub['Topic'] for sub in res]
                #self.assertItemsEqual(expected_subs, actual_subs)
                # https://bugs.python.org/issue17866
                self.assertCountEqual(expected_subs, actual_subs)

class Errors(base.BaseCase):
    @patch('buildercore.core.stack_data')
    def test_no_running_instances_found(self, stack_data):
        stack_data.return_value = []
        self.assertEqual(
            core.stack_all_ec2_nodes('dummy1--test', lambda: True),
            {}
        )

    @patch('buildercore.core.stack_data')
    def test_no_public_ips_available(self, stack_data):
        stack_data.return_value = [
            {'InstanceId': 'i-1', 'PublicIpAddress': None, 'Tags': []},
        ]
        self.assertRaises(
            core.NoPublicIps,
            core.stack_all_ec2_nodes, 'dummy1--test', lambda: True
        )

class TestCoreNewProjectData(base.BaseCase):
    def setUp(self):
        self.dummy1_config = join(self.fixtures_dir, 'dummy1-project.json')
        self.dummy2_config = join(self.fixtures_dir, 'dummy2-project.json')
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

    def tearDown(self):
        pass

    def test_configurations(self):
        expected = [
            ('dummy1', self.dummy1_config),
            ('dummy2', self.dummy2_config),
            ('dummy3', self.dummy3_config),
        ]
        for pname, expected_path in expected:
            expected_data = json.load(open(expected_path, 'r'))
            project_data = project.project_data(pname)
            project_data = utils.remove_ordereddict(project_data)
            self.assertEqual(expected_data, project_data)

    # snippets

    @skip("depends on old project config generation")
    def test_merge_default_snippet(self):
        "merging a snippet into the defaults ensures all projects get that new default"
        # all projects now get 999 cpus. perfectly sane requirement.
        project_data = project.project_data('dummy1')
        project_data = utils.remove_ordereddict(project_data)

        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        self.assertEqual(project_data, expected_data)

    @skip("depends on old project config generation")
    def test_merge_multiple_default_snippets(self):
        """merging multiple overlapping snippets into the defaults
        ensures all projects get the new defaults"""
        # all projects now get 999 cpus. perfectly sane requirement.
        project_data = project.project_data('dummy1')
        project_data = utils.remove_ordereddict(project_data)

        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        expected_data['vagrant']['cpucap'] = 111

        self.assertEqual(project_data, expected_data)

def test_stack_exists():
    stackname = 'foo--bar'
    cases = [
        ("CREATE_COMPLETE", [None, "steady", "active"]),
        ("UPDATE_ROLLBACK_COMPLETE", [None, "steady"]),
        ("UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS", [None])
    ]
    for stack_status, true_state_list in cases:
        mock = Mock(stack_status=stack_status)
        with patch('buildercore.core.describe_stack', return_value=mock):
            for true_state in true_state_list:
                assert core.stack_exists(stackname, state=true_state), stack_status

def test_stack_exists__dne():
    stackname = 'foo--bar'
    exception = botocore.exceptions.ClientError(**{
        'error_response': {'Error': {'Message': 'does not exist'}},
        'operation_name': 'describe'
    })
    with patch('buildercore.core.describe_stack', raises=exception):
        assert not core.stack_exists(stackname)
        assert not core.stack_exists(stackname, state='steady')
        assert not core.stack_exists(stackname, state='active')

def test_stack_exists__bad_state_label():
    stackname = 'foo--bar'
    with patch('buildercore.core.describe_stack'):
        with pytest.raises(AssertionError) as pytest_exc_info:
            core.stack_exists(stackname, state='cursed')
        exc = pytest_exc_info.value
        assert str(exc) == "unsupported state label 'cursed'. supported states: None, active, steady"
