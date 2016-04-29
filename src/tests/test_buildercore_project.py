from . import base
import os
from os.path import join
from buildercore import config, project
from collections import OrderedDict
class TestProject(base.BaseCase):
    def setUp(self):
        self.project_file = join(self.fixtures_dir, 'dummy-project.yaml')
        self.parsed_config = config.parse({
            'project-locations': [self.project_file]})

    def tearDown(self):
        pass

    def test_org_project_map(self):
        prj_loc_lst = self.parsed_config['project-locations']
        res = project.org_project_map(prj_loc_lst)
        self.assertEqual(OrderedDict, type(res))
    
    def test_org_map(self):
        "a map of organisations and their projects are returned"
        prj_loc_lst = self.parsed_config['project-locations']
        expected = {'dummy-project': [
            'dummy1', 'dummy2', 'dummy3'
        ]}
        #self.assertEqual(project.org_project_map(prj_loc_lst), expected)
        self.assertEqual(project.org_map(prj_loc_lst), expected)

    def test_project_list(self):
        "a simple list of projects are returned, ignoring which org they belong to"
        prj_loc_lst = self.parsed_config['project-locations']
        expected = [
            'dummy1', 'dummy2', 'dummy3'
        ]
        self.assertEqual(project.project_list(prj_loc_lst), expected)
