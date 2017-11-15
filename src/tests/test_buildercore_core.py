import json
from os.path import join
from . import base
from buildercore import core, utils, project
from unittest import skip

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
            'int_node_hostname': 'ci--dummy2--%s.example.internal',
        }
        stackname = 'dummy2--ci'
        self.assertEqual(core.hostname_struct(stackname), expected)

    def test_project_name_from_stackname(self):
        expected = [
            ('central-logging--2014-01-14', 'central-logging'),
            ('elife-api--2015-03-10-lsh', 'elife-api'),
            ('elife-api--dummy', 'elife-api'),
            ('elife-api--prod-candidate', 'elife-api'),
            ('elife-arges--2015-03-20', 'elife-arges'),
            ('elife-bot--2015-04-29', 'elife-bot'),
            ('elife-bot--2015-05-11v2', 'elife-bot'),
            ('elife-bot--large-gnott-again-2015-12-13', 'elife-bot'),
            ('elife-ci--2015-03-13', 'elife-ci'),
            ('elife-civiapi--2015-02-13', 'elife-civiapi'),
            ('elife-crm--2015-08-18', 'elife-crm'),
            ('elife-dashboard--2016-01-26', 'elife-dashboard'),
            ('elife-lax--2015-10-15-develop', 'elife-lax'),
            ('elife-metrics--2015-09-25', 'elife-metrics'),
            ('elife-metrics--prod-candidate', 'elife-metrics'),
            ('elife-website--2015-11-12', 'elife-website'),
            ('elife-website--non-article-content-updating', 'elife-website'),
            ('lagotto--2015-03-30', 'lagotto'),
            ('lagotto--testing-2015-05-12', 'lagotto'),
            ('master-server--2014-12-24', 'master-server'),
        ]
        self.assertAllPairsEqual(core.project_name_from_stackname, expected)

    def test_parse_stackname(self):
        expected = [
            ('lax--prod', ['lax', 'prod']),
            ('journal-cms--end2end', ['journal-cms', 'end2end']),
        ]
        self.assertAllPairsEqual(core.parse_stackname, expected)

    def test_master_server_stackname(self):
        self.assertTrue(core.is_master_server_stack('master-server--temp'))
        self.assertFalse(core.is_master_server_stack('master-some-project--end2end'))
        self.assertFalse(core.is_master_server_stack('lax--end2end'))

    def test_is_prod_stack(self):
        self.assertTrue(core.is_prod_stack('lax--prod'))
        self.assertFalse(core.is_prod_stack('lax--end2end'))
        self.assertFalse(core.is_prod_stack('lax--ci'))

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
        results = map(core.is_master_server_stack, true_cases)
        self.assertTrue(all(results), "not all master servers identified: %r" % zip(true_cases, results))

    def test_master_server_identified_false_cases(self):
        false_cases = [
            'master-server', # *stack* names not project names
            '', None, 123, {}, [], self
        ]
        results = map(core.is_master_server_stack, false_cases)
        self.assertFalse(all(results), "not all false cases identified: %r" % zip(false_cases, results))

    def test_find_region(self):
        self.assertEqual(core.find_region(), "us-east-1")

    def test_find_region_when_more_than_one_is_available(self):
        self.switch_in_test_settings('dummy-settings-multiple-regions.yaml')
        try:
            core.find_region()
            self.fail("Shouldn't be able to choose a region")
        except core.MultipleRegionsError as e:
            self.assertEqual(["us-east-1", "eu-central-1"], e.regions())

    def test_find_ec2_instances(self):
        self.assertEquals([], core.find_ec2_instances('dummy1--prod', allow_empty=True))

    def test_find_ec2_instances_requiring_a_non_empty_list(self):
        self.assertRaises(core.NoRunningInstances, core.find_ec2_instances, 'dummy1--prod', allow_empty=False)


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
