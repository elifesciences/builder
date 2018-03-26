from . import base
import json
from os.path import join
from buildercore import config, project, utils
from buildercore.project import files as project_files
from collections import OrderedDict

ALL_PROJECTS = [
    'dummy1', 'dummy2', 'dummy3',
    'just-some-sns', 'project-with-sqs', 'project-with-s3',
    'project-with-ext', 'project-with-cloudfront', 'project-with-cloudfront-minimal',
    'project-with-cloudfront-error-pages', 'project-with-cloudfront-origins', 'project-with-cluster', 'project-with-cluster-suppressed', 'project-with-cluster-overrides', 'project-with-stickiness', 'project-with-multiple-elb-listeners',
    'project-with-cluster-integration-tests', 'project-with-db-params', 'project-with-rds-only', 'project-with-elasticache-redis', 'project-with-multiple-elasticaches', 'project-with-fully-overridden-elasticaches',
]

class TestProject(base.BaseCase):
    def setUp(self):
        self.project_file = join(self.fixtures_dir, 'projects', 'dummy-project.yaml')
        self.parsed_config = config.parse({
            'project-locations': [self.project_file]})

    def tearDown(self):
        pass

    def test_org_project_map(self):
        prj_loc_lst = self.parsed_config['project-locations']
        res = project.org_project_map(prj_loc_lst)
        self.assertEqual(OrderedDict, type(res))

    def test_org_map(self):
        "a map of organisations and their projects are returned"
        prj_loc_lst = self.parsed_config['project-locations']
        expected = {'dummy-project': ALL_PROJECTS}
        #self.assertEqual(project.org_project_map(prj_loc_lst), expected)
        self.assertEqual(project.org_map(prj_loc_lst), expected)

    def test_project_list(self):
        "a simple list of projects are returned, ignoring which org they belong to"
        prj_loc_lst = self.parsed_config['project-locations']
        expected = ALL_PROJECTS
        self.assertEqual(project.project_list(prj_loc_lst), expected)


class TestProjectData(base.BaseCase):
    def setUp(self):
        project.files.all_projects.cache_clear()
        self.dummy_yaml = join(self.fixtures_dir, 'projects', 'dummy-project.yaml')
        self.dummy1_config = join(self.fixtures_dir, 'dummy1-project.json')
        self.dummy2_config = join(self.fixtures_dir, 'dummy2-project.json')
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

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

    def test_merge_default_snippet(self):
        "merging a snippet into the defaults ensures all projects get that new default"
        # all projects now get 999 cpus. perfectly sane requirement.
        snippet = {'defaults':
                   {'vagrant': {
                       'cpus': 999}}}
        project_data = project_files.project_data('dummy1', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)

        # load up the expected fixture and switch the value ...
        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        # ... then compare to actual
        self.assertEqual(project_data, expected_data)

    def test_deep_merge_default_snippet_but_excluded(self):
        """merging a snippet into the defaults ensures all projects get that new default.
        snippet is ignored if project is excluding that section"""

        cases = [
            {'defaults': {'aws': {'rds': {'subnets': ['subnet-baz']}}}},
            {'defaults': {'aws': {'ext': {'size': 999}}}},
            {'defaults': {'aws-alt': {'rds': {'storage': 999}}}},
            {'defaults': {'aws-alt': {'ext': {'size': 999}}}},
        ]
        for snippet in cases:
            project_data = project_files.project_data('dummy1', self.dummy_yaml, [snippet])
            project_data = utils.remove_ordereddict(project_data)
            expected_data = json.load(open(self.dummy1_config, 'r'))
            # dummy1 project has no rds, ext or alt-aws configs using those. nothing should have changed
            self.assertEqual(project_data, expected_data)

    def test_deep_merge_default_random_snippet(self):
        """merging a snippet of un-ignored garbage into the defaults ensures all projects
        get that new default, even if it's deeply nested"""
        snippet = {'defaults':
                   {'foo': {
                       'bar': {
                           'baz': ['bup']}}}}
        project_data = project_files.project_data('dummy1', self.dummy_yaml, [snippet])
        self.assertEqual(project_data['foo']['bar']['baz'][0], 'bup')

    def test_deep_merge_default_snippet2_project3(self):
        """merging a snippet into the defaults ensures all projects and their alternative configuration
        also get that new default, even if it's deeply nested"""
        snippet = {'defaults':
                   {'aws': {
                       'rds': {
                           'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy3', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)
        self.assertEqual(project_data['aws-alt']['alt-config1']['rds']['subnets'][0], 'subnet-baz')

    def test_deep_merge_default_snippet_altconfig(self):
        """merging a snippet into the defaults ensures all projects get that new default,
        even alternative configurations, even if it's deeply nested"""

        # dummy2 project DOES NOT provide any subnet overrides. it should inherit this override
        snippet = {'defaults':
                   {'aws': {
                       'rds': {
                           'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy2', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)

        self.assertEqual(project_data['aws']['rds']['subnets'][0], 'subnet-baz')
        self.assertEqual(project_data['aws-alt']['alt-config1']['rds']['subnets'][0], 'subnet-baz')
        self.assertEqual(project_data['aws-alt']['fresh']['rds']['subnets'][0], 'subnet-baz')

        # load up the expected fixture and switch the value ...
        expected_data = json.load(open(self.dummy2_config, 'r'))
        expected_data['aws']['rds']['subnets'] = ['subnet-baz']
        expected_data['aws-alt']['alt-config1']['rds']['subnets'] = ['subnet-baz']
        expected_data['aws-alt']['fresh']['rds']['subnets'] = ['subnet-baz']

        # ... then compare to actual
        self.assertEqual(expected_data, project_data)

    def test_deep_merge_project_snippet(self):
        """merging a snippet into the defaults ensures all projects get that new default,
        even alternative configurations, even if it's deeply nested"""

        # dummy1 ordinarily has no RDS settings at all.
        # by updating the project settings, I expect it to now have the rds section with the overrides
        snippet = {'dummy1':
                   {'aws': {
                       'rds': {
                           'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy1', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)
        self.assertEqual(project_data['aws']['rds']['subnets'][0], 'subnet-baz')

    def test_deep_merge_project_snippet_altconfig(self):
        """merging a snippet into the defaults ensures all projects get that new default,
        even alternative configurations, even if it's deeply nested"""

        # dummy3 only has no RDS settings in it's alt-config section
        # by updating the project settings, I expect it to now have the rds section with the overrides
        # and for the altconfigs to replicate that
        snippet = {'dummy3':
                   {'aws': {
                       'rds': {
                           'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy3', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)

        self.assertEqual(project_data['aws']['rds']['subnets'][0], 'subnet-baz')
        self.assertEqual(project_data['aws-alt']['alt-config1']['rds']['subnets'][0], 'subnet-baz')

    def test_merge_multiple_default_snippets(self):
        """merging multiple overlapping snippets into the defaults
        ensures all projects get the new defaults"""
        # all projects now get 999 cpus. perfectly sane requirement.
        snippet = {'defaults':
                   {'vagrant': {
                       'cpucap': 10,  # to be overriden by the override
                       'cpus': 999}}}
        snippet2 = {'defaults':
                    {'vagrant': {
                        'cpucap': 111}}}
        snippet_list = [snippet, snippet2]
        project_data = project_files.project_data('dummy1', self.dummy_yaml, snippet_list)
        project_data = utils.remove_ordereddict(project_data)

        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        expected_data['vagrant']['cpucap'] = 111
        self.assertEqual(project_data, expected_data)


class TestMultiProjects(base.BaseCase):
    def setUp(self):
        loaded_config = {
            'project-locations': [
                join(self.fixtures_dir, 'projects', 'dummy-project.yaml'),
                join(self.fixtures_dir, 'projects', 'dummy-project2.yaml'),
            ]
        }
        self.parsed_config = config.parse(loaded_config)['project-locations']

    def tearDown(self):
        pass

    def test_project_list_from_multiple_files(self):
        expected = ALL_PROJECTS + ['yummy1']
        self.assertEqual(project.project_list(self.parsed_config), expected)
