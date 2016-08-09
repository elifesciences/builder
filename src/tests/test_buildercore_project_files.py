from . import base
import os
from os.path import join
from buildercore.project import files
from collections import OrderedDict

class TestFiles(base.BaseCase):
    def setUp(self):
        # TODO: call parent setUp
        self.project_file = join(self.fixtures_dir, 'projects', 'dummy-project.yaml')

    def test_all_projects(self):
        defaults, projects = files.all_projects(self.project_file)
        self.assertIsInstance(defaults, OrderedDict)
        self.assertIn('description', defaults)
        self.assertIsInstance(projects, OrderedDict)
        self.assertIn('dummy1', projects)
        self.assertIsInstance(projects['dummy1'], OrderedDict)
        self.assertIn('repo', projects['dummy1'])
        self.assertIn('aws', projects['dummy1'])
        self.assertIn('vagrant', projects['dummy1'])
