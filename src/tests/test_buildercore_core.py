import pssh.exceptions
from moto import mock_rds
import pytest
from functools import partial
import json
from os.path import join
from . import base
from buildercore import core, utils, project, command
from unittest import skip
from unittest.mock import patch, Mock
import botocore

class SimpleCases(base.BaseCase):
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
        # lsh@2022-02-23: added new project to `dummy-project.yaml` with a different aws region.
        # this means calling `find_region` without a stack will now find multiple regions and die.
        #self.assertEqual(core.find_region(), "us-east-1")
        self.assertEqual(core.find_region("dummy1--foo"), "us-east-1")
        self.assertEqual(core.find_region("project-with-fastly-shield-aws-region--bar"), "eu-central-1")

    def test_find_region_when_more_than_one_is_available(self):
        try:
            core.find_region()
            self.fail("Shouldn't be able to choose a region")
        except core.MultipleRegionsError as e:
            self.assertCountEqual(["us-east-1", "eu-central-1"], e.regions())

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
    @patch('buildercore.core.ec2_data')
    def test_no_running_instances_found(self, stack_data):
        stack_data.return_value = []
        self.assertEqual(
            core.stack_all_ec2_nodes('dummy1--test', lambda: True),
            {}
        )

    @patch('buildercore.core.ec2_data')
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
            # cp /tmp/dummy*-project.json src/tests/fixtures/
            #json.dump(project_data, open('/tmp/%s-project.json' % pname, 'w'), indent=4)
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

def test_rds_iid():
    "values are slugified into valid rds iids"
    cases = [
        ('a', 'a'),
        ('laxprod', 'laxprod'),
        ('lax--prod', 'lax-prod'),
        ('lax--1--2---3----4', 'lax-1-2-3-4')
    ]
    for given, expected in cases:
        assert core.rds_iid(given) == expected

def test_rds_iid__replacement_num():
    "a replacement number can be passed to suffix the generated rds iid"
    cases = [
        ('a', 0, 'a'),
        ('a', 1, 'a-1'),
        ('a', 99, 'a-99'),
        ('1', 1, '1-1'),
        ('lax--prod', 2, 'lax-prod-2'),
        ('lax--1---2----3-----4', 5, 'lax-1-2-3-4-5')
    ]
    for given, replacement, expected in cases:
        assert core.rds_iid(given, replacement) == expected

def test_rds_iid__bad_cases():
    "bad inputs to `rds_iid` raise `AssertionError`s"
    cases = [
        None, '', '-', {}
    ]
    for given in cases:
        with pytest.raises(AssertionError):
            core.rds_iid(given)


@mock_rds
def test_find_rds_instances(test_projects):
    "an rds instance is found with the correct rds iid."
    stackname = "dummy1--bar"
    rds_iid = expected = "dummy1-bar"
    conn = core.boto_client('rds', 'us-east-1')
    conn.create_db_instance(DBInstanceIdentifier=rds_iid, DBInstanceClass="db.t2.small", Engine="postgres")
    context = {}
    with patch('buildercore.context_handler.load_context', return_value=context):
        actual = core.find_rds_instances(stackname)
        assert actual[0]['DBInstanceIdentifier'] == expected

@mock_rds
def test_find_rds_instances__replacement(test_projects):
    "the correct rds iid is generated when `rds.num-replacements` is set in project's context."
    stackname = "dummy1--bar"
    rds_iid = expected = "dummy1-bar-99"
    conn = core.boto_client('rds', 'us-east-1')
    conn.create_db_instance(DBInstanceIdentifier=rds_iid, DBInstanceClass="db.t2.small", Engine="postgres")
    context = {'rds': {'num-replacements': 99}}
    with patch('buildercore.context_handler.load_context', return_value=context):
        actual = core.find_rds_instances(stackname)
        assert actual[0]['DBInstanceIdentifier'] == expected

@patch('buildercore.core.ec2_data', return_value=[
    {'InstanceId': 'foo', 'PublicIpAddress': '0', 'Tags': []}
])
def test_stack_all_ec2_nodes__network_retry_logic(_):
    "NetworkErrors are caught and retried N times"
    expected = 6
    retried = 0

    def raiser(*args, **kwargs):
        nonlocal retried
        retried += 1
        raise pssh.exceptions.ConnectionErrorException("foo")
    m = Mock()
    m.run_command = raiser
    stackname = "foo--bar"
    with patch('buildercore.threadbare.operations._ssh_client', return_value=m):
        core.stack_all_ec2_nodes(
            stackname,
            (command.remote, {'command': "echo 'hello world'"}),
            abort_on_prompts=True,
            # 'retried' isn't updated on our thread when run using 'parallel'
            concurrency='serial'
        )
        assert retried == expected
