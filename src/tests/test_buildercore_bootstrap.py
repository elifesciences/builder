from . import base
from buildercore import bootstrap
from buildercore.utils import yaml_dumps

class TestBuildercoreBootstrap(base.BaseCase):
    def test_master_configuration(self):
        formulas = ['https://github.com/elifesciences/journal-formula', 'https://github.com/elifesciences/lax-formula']
        master_configuration_template = open('src/tests/fixtures/etc-salt-master.template', 'r')
        master_configuration = bootstrap.expand_master_configuration(master_configuration_template, formulas)
        master_configuration_yaml = yaml_dumps(master_configuration)
        expected_configuration = """auto_accept: true
interface: 0.0.0.0
log_level: info
fileserver_backend:
- roots
file_roots:
    base:
    - /opt/builder-private/salt/
    - /opt/formulas/journal/salt/
    - /opt/formulas/lax/salt/
    - /opt/formulas/builder-base/
pillar_roots:
    base:
    - /opt/builder-private/pillar
"""
        self.assertEqual(master_configuration_yaml, expected_configuration)

    def test_sub_sqs(self):
        self.fail()
