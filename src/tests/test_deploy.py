from .base import BaseCase
from deploy import build_stack_name

class TestDeployTasks(BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_deploy_task(self):
        "a deploy task exists"

    def test_building_stack_names(self):
        self.assertEqual(build_stack_name('lax', 'master'), 'lax--master')
        self.assertEqual(build_stack_name('lax', 'master', 'ci'), 'lax--master--ci')


        
