from . import base
from buildercore import bootstrap

class TestBuildercoreBootstrap(base.BaseCase):
    def test_master_configuration(self):
        formulas = ['https://github.com/elifesciences/journal-formula', 'https://github.com/elifesciences/lax-formula']
        master_configuration_template = open('src/tests/fixtures/etc-salt-master.template', 'r')
        master_configuration = bootstrap.render_master_configuration(master_configuration_template, formulas).getvalue()
        expected_configuration = """auto_accept: true
interface: 0.0.0.0
log_level: info
fileserver_backend:
- roots
file_roots:
    base:
    - /opt/builder-private/salt/
    - /opt/formulas/journal/
    - /opt/formulas/lax/
    - /opt/formulas/builder-base/
pillar_roots:
    base:
    - /opt/builder-private/pillar
"""
        self.assertEqual(master_configuration, expected_configuration)
