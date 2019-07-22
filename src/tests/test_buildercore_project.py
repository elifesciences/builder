from . import base
import json
from os.path import join
from buildercore import config, project, utils

ALL_PROJECTS = [
    'dummy1', 'dummy2', 'dummy3',
    'just-some-sns', 'project-with-sqs', 'project-with-s3',
    'project-with-ext', 'project-with-cloudfront', 'project-with-cloudfront-minimal',
    'project-with-cloudfront-error-pages', 'project-with-cloudfront-origins', 'project-with-fastly-minimal', 'project-with-fastly-complex', 'project-with-fastly-gcs', 'project-with-fastly-bigquery', 'project-with-fastly-shield', 'project-with-fastly-shield-pop',
    'project-with-ec2-custom-root', 'project-with-ec2-t2-unlimited',
    'project-with-cluster', 'project-with-cluster-suppressed', 'project-with-cluster-overrides', 'project-with-cluster-empty',
    'project-with-stickiness', 'project-with-multiple-elb-listeners',
    'project-with-cluster-integration-tests', 'project-with-db-params', 'project-with-rds-only', 'project-with-rds-encryption', 'project-with-elasticache-redis', 'project-with-multiple-elasticaches', 'project-with-fully-overridden-elasticaches',
    'project-on-gcp', 'project-with-bigquery-datasets-only', 'project-with-bigquery', 'project-with-bigquery-remote-schemas',
    'project-with-eks', 'project-with-eks-helm',
]

class TestProject(base.BaseCase):
    def setUp(self):
        self.project_file = join(self.fixtures_dir, 'projects', 'dummy-project.yaml')
        self.parsed_config = {
            'project-locations': config.parse_loc_list([self.project_file])
        }

    def tearDown(self):
        pass

    def test_project_list(self):
        "a simple list of projects are returned, ignoring which org they belong to"
        expected = ALL_PROJECTS + ['yummy1']
        self.assertEqual(project.project_list(), expected)


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
