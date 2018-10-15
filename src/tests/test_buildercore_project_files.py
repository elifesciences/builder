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
        self.assertIn('rds', list(dummy2['aws-alt']['alt-config1'].keys()))
        self.assertNotIn('elb', list(dummy2['aws-alt']['alt-config1'].keys()))
        self.assertNotIn('cloudfront', list(dummy2['aws-alt']['alt-config1'].keys()))

    def test_project_aws_alt_integer_names_should_be_converted_to_string(self):
        self.assertEqual(
            files.project_aws_alt(
                {1804: {'ec2': {'ami': 'ami-22222222'}}},
                project_base_aws={},
                global_aws={}
            ),
            {'1804': {'ec2': {'ami': 'ami-22222222'}}},
        )
