import json
from os.path import join
from . import base
from buildercore import core, utils, project
from unittest import skip

class SimpleCases(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    @skip("relies on actual project data")
    def test_mk_hostname(self):

        # this test needs fixtures!!
        
        expected_triples = [
            ('elife-lax', 'elife-lax--develop', 'develop.lax'),
            ('elife-lax', 'elife-lax--feature-asdf', 'feature-asdf.lax'),
            ('elife-lax', 'elife-lax--master', 'master.lax'),
            ('master-server', 'master--develop', None), # no subdomain
        ]
        for project, stackname, expected in expected_triples:
            actual = core.mk_hostname(stackname)
            try:
                self.assertEqual(expected, actual)
            except AssertionError:
                print 'expected %r got %r' % (expected, actual)
                raise

    def test_mk_stackname(self):
        cases = [
            (['lax', 'develop'], 'lax--develop'),
            (['elife-lax', 'develop'], 'elife-lax--develop'),
            (['master-server-2', 'master'], 'master-server-2--master'),

            # with a cluster id
            (['lax', 'develop', 'ci'], 'lax--develop--ci'),
            (['master-server-2', 'master', 'testing-2'], 'master-server-2--master--testing-2')
        ]
        for bits, expected in cases:
            self.assertEqual(core.mk_stackname(*bits), expected)
            
    def test_project_name_from_stackname(self):
        expected = [
            ('central-logging--2014-01-14', 'central-logging'),
            ('elife-api--2015-03-10-lsh', 'elife-api'),
            ('elife-api--dummy', 'elife-api'),
            ('elife-api--prod-candidate', 'elife-api'),
            ('elife-arges--2015-03-20', 'elife-arges'),
            ('elife-bot--2015-04-29', 'elife-bot'),
            ('elife-bot--2015-05-11v2', 'elife-bot'),
            ('elife-bot--large-gnott-again-2015-12-13', 'elife-bot'),
            ('elife-ci--2015-03-13', 'elife-ci'),
            ('elife-civiapi--2015-02-13', 'elife-civiapi'),
            ('elife-crm--2015-08-18', 'elife-crm'),
            ('elife-dashboard--2016-01-26', 'elife-dashboard'),
            ('elife-jira--2015-06-02', 'elife-jira'),
            ('elife-lax--2015-10-15-develop', 'elife-lax'),
            ('elife-metrics--2015-09-25', 'elife-metrics'),
            ('elife-metrics--prod-candidate', 'elife-metrics'),
            ('elife-website--2015-11-12', 'elife-website'),
            ('elife-website--non-article-content-updating', 'elife-website'),
            ('lagotto--2015-03-30', 'lagotto'),
            ('lagotto--testing-2015-05-12', 'lagotto'),
            ('master-server--2014-12-24', 'master-server'),            
        ]
        self.assertAllPairsEqual(core.project_name_from_stackname, expected)

    def test_bad_pname_from_stackname(self):
        expected_error = [
            # project names by themselves. a stackname must be projectname + instance_id
            'elife-lax',
            # master server isn't special here
            'master-server',
            'asdf', # project name that doesn't exist
            # just bad values
            '', None, -1,
        ]
        for expected in expected_error:
            self.assertRaises(ValueError, core.project_name_from_stackname, expected)

    def test_master_server_identified(self):
        true_cases = [
            'master-server--master',
            'master-server--2016-01-01',
            'master-server--master--ci',
        ]
        results = map(core.is_master_server_stack, true_cases)
        if False in results:
            print zip(true_cases, results)
        self.assertTrue(all(results))

    def test_master_server_identified_false_cases(self):
        false_cases = [
            'master-server', # *stack* names not project names
            '', None, 123, {}, [], self
        ]
        results = map(core.is_master_server_stack, false_cases)
        if False in results:
            print zip(false_cases, results)
        self.assertFalse(all(results))
        
            

# 
# these might be better off in the test_buildercore_project 
# 
            
class TestCoreProjectData(base.BaseCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_just_branch_deployable_projects(self):
        "projects that are deployable by their branch are accurately filtered from the list of all projects"
        assert(False), "this test is poorly self contained"
        all_projects = project.project_list() # maybe?
        branch_deployable = project.branch_deployable_projects()
        self.assertTrue(len(all_projects) > len(branch_deployable))
        self.assertTrue(len(branch_deployable) > 0)
        self.assertTrue(branch_deployable.has_key('elife-api'))

class TestCoreNewProjectData(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, "dummy-project.yaml")
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
            try:
                expected_data = json.load(open(expected_path, 'r'))
                #project_data = project.project_data(pname, project_file=self.project_config)
                project_data = project.project_data(pname) #, project_file=self.project_config)
                project_data = utils.remove_ordereddict(project_data)
                self.assertEqual(expected_data, project_data)
            except AssertionError:
                print 'failed',pname
                raise

    # snippets

    @skip("depends on old project config generation")
    def test_merge_default_snippet(self):
        "merging a snippet into the defaults ensures all projects get that new default"
        # all projects now get 999 cpus. perfectly sane requirement.
        snippet = {'defaults':
                       {'vagrant': {
                           'cpus': 999}}}
        #project_data = project.project_data('dummy1', self.project_config, [snippet])
        project_data = project.project_data('dummy1') #, self.project_config, [snippet])
        project_data = utils.remove_ordereddict(project_data)
        
        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        self.assertEqual(project_data, expected_data)
        
    @skip("depends on old project config generation")
    def test_merge_multiple_default_snippets(self):
        """merging multiple overlapping snippets into the defaults 
        ensures all projects get the new defaults"""
        # all projects now get 999 cpus. perfectly sane requirement.
        snippet = {'defaults':
                       {'vagrant': {
                           'cpucap': 10,  # overriden by the override
                           'cpus': 999}}}
        snippet2 = {'defaults':
                        {'vagrant': {
                            'cpucap': 111}}}
        snippet_list = [snippet, snippet2]
        #project_data = project.project_data('dummy1', self.project_config, snippet_list)
        project_data = project.project_data('dummy1') #, self.project_config, snippet_list)
        project_data = utils.remove_ordereddict(project_data)
        
        expected_data = json.load(open(self.dummy1_config, 'r'))
        expected_data['vagrant']['cpus'] = 999
        expected_data['vagrant']['cpucap'] = 111
        
        self.assertEqual(project_data, expected_data)
