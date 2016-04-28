from . import base
import os
from os.path import join
from buildercore import config, project
from collections import OrderedDict

class ParseConfig(base.BaseCase):
    def setUp(self):
        self.settings_file_path = join(config.PROJECT_PATH, 'example.settings.yml')
        

    def tearDown(self):
        pass

    def test_load(self):
        loaded_config = config.load(self.settings_file_path)
        expected_config = OrderedDict([
            ('project-locations', [
                './projects/',
                './projects/example.yaml',
                '~/dev/python/builder/',
                'ssh://master.elifesciences.org/projects/',
                'https://master.elifesciences.org/projects/'
            ]),
        ])
        self.assertEqual(loaded_config, expected_config)

    def test_parse(self):
        loaded_config = config.load(self.settings_file_path)
        parsed_config = config.parse(loaded_config)
        user_path = os.path.expanduser('~')
        expected_config = OrderedDict([
            ('project-locations', [
                ('file', None, join(config.PROJECT_PATH, 'projects', 'example.yaml')),
                ('ssh', 'master.elifesciences.org', '/projects/'),
                ('https', 'master.elifesciences.org', '/projects/')
            ]),
        ])
        self.assertEqual(parsed_config, expected_config)

class ASDF(base.BaseCase):
    def setUp(self):
        self.project_file = join(self.fixtures_dir, 'dummy-project.yaml')
        self.parsed_config = config.parse({
            'project-locations': [os.path.dirname(self.project_file)]})

    def tearDown(self):
        pass

    def test_project_list(self):
        prj_loc_lst = self.parsed_config['project-locations']
        expected = {'dummy-project': [
            'dummy1', 'dummy2', 'dummy3'
        ]}
        self.assertEqual(project.project_list(prj_loc_lst), expected)
