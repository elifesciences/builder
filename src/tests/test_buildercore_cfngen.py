from time import sleep
from . import base
from buildercore import cfngen, project, context_handler

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
        context = self._base_context()
        delta = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta, {'Outputs': {}, 'Resources': {}})

    def test_template_delta_includes_cloudfront(self):
        "we can add CDNs (that takes an hour or more) without downtime"
        context = self._base_context()
        context['full_hostname'] = "test--dummy1.example.org"
        context['cloudfront'] = {
            "subdomains": [
                "test--cdn-dummy1"
            ],
            "subdomains-without-dns": [],
            "compress": True,
            "cookies": [],
            "certificate_id": "AAAA...",
            "headers": [],
            "errors": None,
            "default-ttl": 300,
        }
        delta = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1', 'ExtDNS'])
        self.assertEqual(delta['Outputs'].keys(), ['DomainName'])

    def test_template_delta_does_not_include_cloudfront_if_there_are_no_modifications(self):
        context = self._base_context('project-with-cloudfront-minimal')
        delta = cfngen.template_delta('project-with-cloudfront-minimal', context)
        self.assertEqual(delta['Resources'].keys(), [])
        self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_does_not_normally_include_ec2(self):
        "we do not want to mess with running VMs"
        context = self._base_context()
        context['ec2']['cluster_size'] = 2
        delta = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta['Resources'].keys(), [])
        self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_includes_ec2_instance_type(self):
        "we accept to reboot VMs if an instance type change is requested"
        context = self._base_context()
        context['ec2']['type'] = 't2.xlarge'
        delta = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta['Resources'].keys(), ['EC2Instance1'])
        self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_includes_parts_of_cloudfront(self):
        "we want to update CDNs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cloudfront-minimal')
        context['cloudfront']['subdomains'] = [
            "custom-subdomain"
        ]
        delta = cfngen.template_delta('project-with-cloudfront-minimal', context)
        self.assertEqual(delta['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1'])
        self.assertEqual(delta['Resources']['CloudFrontCDNDNS1']['Properties']['Name'], 'custom-subdomain.example.org.')
        self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_includes_parts_of_elb(self):
        "we want to update ELBs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cluster')
        context['elb']['healthcheck']['protocol'] = 'tcp'
        delta = cfngen.template_delta('project-with-cluster', context)
        self.assertEqual(delta['Resources'].keys(), ['ElasticLoadBalancer'])
        self.assertEqual(delta['Resources']['ElasticLoadBalancer']['Properties']['HealthCheck']['Target'], 'TCP:80')
        self.assertEqual(delta['Outputs'].keys(), [])

    def test_template_delta_includes_new_external_volumes(self):
        "we want to add additional volumes to projects that are getting their main volume filled"
        context = self._base_context()
        context['ext'] = {
            'size': 10,
            'device': '/dev/sdh',
        }
        delta = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta['Resources'].keys(), ['MountPoint1', 'ExtraStorage1'])
        self.assertEqual(delta['Resources']['ExtraStorage1']['Properties']['Size'], '10')
        self.assertEqual(delta['Resources']['MountPoint1']['Properties']['Device'], '/dev/sdh')
        self.assertEqual(delta['Outputs'].keys(), [])

    def _base_context(self, project_name='dummy1'):
        stackname = '%s--test' % project_name
        context = cfngen.build_context(project_name, stackname=stackname)
        context_handler.write_context(stackname, context)
        template = cfngen.render_template(context)
        cfngen.write_template(stackname, template)
        return context
