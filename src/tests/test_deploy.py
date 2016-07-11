from .base import BaseCase
from deploy import build_stack_name

class TestDeployTasks(BaseCase):
    def test_building_stack_names(self):
        self.assertEqual(build_stack_name('lax', 'end2end'), 'lax--end2end')
