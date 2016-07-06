from pprint import pprint
from os.path import join
import json
from . import base
from buildercore import cfngen, trop, config, utils

class TestBuildercoreTrop(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

    def tearDown(self):
        pass

    def test_rds_template_contains_rds(self):
        extra = {
            'instance_id': 'dummy3--test',
            'alt-config': 'alt-config1'
        }
        context = cfngen.build_context('dummy3', **extra)
        self.assertEqual(context['rds_instance_id'], "dummy3test")
        self.assertTrue(context['project']['aws'].has_key('rds'))
        cfn_template = trop.render(context)
        data = json.loads(trop.render(context))
        self.assertTrue(isinstance(utils.lu(data, 'Resources.AttachedDB'), dict))
