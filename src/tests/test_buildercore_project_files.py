from . import base
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

    def test_dummy2_aws_alt_should_not_have_incomplete_defaults_for_cloudfront(self):
        dummy2 = files.project_data('dummy2', self.project_file)
        self.assertIn('rds', dummy2['aws-alt']['alt-config1'].keys())
        self.assertNotIn('elb', dummy2['aws-alt']['alt-config1'].keys())
        self.assertNotIn('cloudfront', dummy2['aws-alt']['alt-config1'].keys())
