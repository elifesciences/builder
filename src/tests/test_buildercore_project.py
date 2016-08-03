from . import base
import os, json
from os.path import join
from buildercore import config, project, utils
from buildercore.project import files as project_files
from collections import OrderedDict
from unittest import skip


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
        expected = {'dummy-project': [
            'dummy1', 'dummy2', 'dummy3'
        ]}
        #self.assertEqual(project.org_project_map(prj_loc_lst), expected)
        self.assertEqual(project.org_map(prj_loc_lst), expected)

    def test_project_list(self):
        "a simple list of projects are returned, ignoring which org they belong to"
        prj_loc_lst = self.parsed_config['project-locations']
        expected = [
            'dummy1', 'dummy2', 'dummy3'
        ]
        self.assertEqual(project.project_list(prj_loc_lst), expected)


class TestProjectData(base.BaseCase):
    def setUp(self):
        self.dummy_yaml = join(self.fixtures_dir, 'projects', 'dummy-project.yaml')
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
            self.assertEqual(expected_data, project_data, 'failed %s' % pname)

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

    def test_deep_merge_default_snippet(self):
        "merging a snippet into the defaults ensures all projects get that new default, even if it's deeply nested"
        snippet = {'defaults':
                       {'aws': {
                           'rds': {
                               'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy1', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)

        # load up the expected fixture and switch the value ...
        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['aws'].get('rds', {}).get('subnets', [''])[0] = 'subnet-baz'
        # ... then compare to actual
        # HANG ON! dummy1 project HAS NO RDS. how is this passing???
        assertTrue(False)
        self.assertEqual(project_data, expected_data)

    def test_deep_merge_default_snippet_altconfig(self):
        """merging a snippet into the defaults ensures all projects get that new default, 
        even alternative configurations, even if it's deeply nested"""
        snippet = {'defaults':
                       {'aws': {
                           'rds': {
                               'subnets': ['subnet-baz']}}}}
        project_data = project_files.project_data('dummy2', self.dummy_yaml, [snippet])
        project_data = utils.remove_ordereddict(project_data)

        # load up the expected fixture and switch the value ...
        expected_data = json.load(open(self.dummy2_config, 'r'))
        expected_data['aws']['rds']['subnets'] = ['subnet-baz']
        expected_data['aws-alt']['alt-config1']['rds']['subnets'] = ['subnet-baz']
        # ... then compare to actual
        self.assertEqual(expected_data, project_data)

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
        expected = [
            'dummy1', 'dummy2', 'dummy3',
            'yummy1'
        ]
        self.assertEqual(project.project_list(self.parsed_config), expected)
