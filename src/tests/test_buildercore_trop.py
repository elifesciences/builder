from os.path import join
import json
from . import base
from buildercore import cfngen, trop, config, utils

class TestBuildercoreTrop(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, "dummy-project.yaml")
        self.dummy3_config = join(self.fixtures_dir, 'dummy3-project.json')

    def tearDown(self):
        pass

    def test_rds_template_contains_rds(self):
        extra = {
            'instance_id': 'dummy3-test',
            'alt-config': 'alt-config1'
        }
        #context = cfngen.build_context('dummy3', self.project_config, config.PILLAR_DIR, **extra)
        #context = cfngen.build_context('dummy3', self.project_config, **extra)
        context = cfngen.build_context('dummy3', **extra)
        self.assertTrue(context['project']['aws'].has_key('rds'))
        data = json.loads(trop.render(context))
        #pprint(data)
        self.assertTrue(isinstance(utils.lu(data, 'Resources.AttachedDB'), dict))
