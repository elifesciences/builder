from time import sleep
from . import base
from buildercore import cfngen, project, context_handler
from mock import patch

import logging
LOG = logging.getLogger(__name__)

class TestBuildercoreCfngen(base.BaseCase):
    def setUp(self):
        self.test_region = 'us-east-1'

    def tearDown(self):
        pass

    def test_rendering(self):
        for pname in project.aws_projects().keys():
            LOG.info('rendering %s', pname)
            cfngen.quick_render(pname)

    def test_validation(self):
        "dummy projects and their alternative configurations pass validation"
        for pname in project.aws_projects().keys():
            self.assertTrue(cfngen.validate_project(pname))
            sleep(0.25)

    def test_validation_elife_projects(self):
        "elife projects (and their alternative configurations) that come with the builder pass validation"

        # HERE BE DRAGONS
        # resets the testing config.SETTINGS_FILE we set in the base.BaseCase class
        self.switch_out_test_settings()

        for pname in project.aws_projects().keys():
            self.assertTrue(cfngen.validate_project(pname))
            sleep(0.5)

        self.switch_in_test_settings()

    def test_empty_template_delta(self):
        template = cfngen.quick_render('dummy1')
        cfngen.write_template('dummy1--test', template)
        delta = cfngen.template_delta('dummy1', stackname='dummy1--test')
        self.assertEqual(delta, {'Outputs': {}, 'Resources': {}})

    def test_template_delta_includes_cloudfront(self):
        "we can add CDNs (that takes an hour or more) without downtime"
        context = self._base_context()
        with patch('buildercore.cfngen.build_context') as mock_build_context:
            context['full_hostname'] = "test--dummy1.example.org"
            context['cloudfront'] = {
                "subdomains": [
                    "test--cdn-dummy1"
                ],
                "compress": True,
                "cookies": [],
                "certificate_id": "AAAA...",
                "headers": [],
                "errors": None,
            }
            mock_build_context.return_value = context
            delta = cfngen.template_delta('dummy1', stackname='dummy1--test')
            self.assertEqual(delta['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1', 'ExtDNS'])
            self.assertEqual(delta['Outputs'].keys(), ['DomainName'])

    def test_template_delta_does_not_include_cloudfront_if_there_are_no_modifications(self):
        context = self._base_context('project-with-cloudfront-minimal')
        with patch('buildercore.cfngen.build_context') as mock_build_context:
            mock_build_context.return_value = context
            delta = cfngen.template_delta('project-with-cloudfront-minimal', stackname='project-with-cloudfront-minimal--test')
            self.assertEqual(delta['Resources'].keys(), [])
            self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_never_includes_ec2(self):
        "we do not want to mess with running VMs"
        context = self._base_context()
        with patch('buildercore.cfngen.build_context') as mock_build_context:
            context['ec2']['cluster_size'] = 2
            mock_build_context.return_value = context
            delta = cfngen.template_delta('dummy1', stackname='dummy1--test')
            self.assertEqual(delta['Resources'].keys(), [])
            self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_includes_parts_of_cloudfront(self):
        "we want to update CDNs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cloudfront-minimal')
        with patch('buildercore.cfngen.build_context') as mock_build_context:
            context['cloudfront']['subdomains'] = [
                "custom-subdomain"
            ]
            mock_build_context.return_value = context
            delta = cfngen.template_delta('project-with-cloudfront-minimal', stackname='project-with-cloudfront-minimal--test')
            self.assertEqual(delta['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1'])
            self.assertEqual(delta['Resources']['CloudFrontCDNDNS1']['Properties']['Name'], 'custom-subdomain.example.org')
            self.assertEqual(delta['Outputs'].keys(), [])

    def _base_context(self, project_name='dummy1'):
        stackname = '%s--test' % project_name
        context = cfngen.build_context(project_name, stackname=stackname)
        context_handler.write_context(stackname, context)
        template = cfngen.render_template(context)
        cfngen.write_template(stackname, template)
        return context
