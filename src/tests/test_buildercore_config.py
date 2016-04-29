from . import base
import os
from os.path import join
from buildercore import config
from collections import OrderedDict

class ParseConfig(base.BaseCase):
    def setUp(self):
        self.settings_file_path = join(self.fixtures_dir, 'dummy-settings.yaml')

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
