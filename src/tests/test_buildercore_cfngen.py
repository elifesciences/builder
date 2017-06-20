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
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus, {'Outputs': {}, 'Resources': {}})

    def test_template_delta_includes_cloudfront(self):
        "we can add CDNs (that takes an hour or more) without downtime"
        context = self._base_context()
        context['full_hostname'] = "test--dummy1.example.org"
        context['cloudfront'] = {
            "subdomains": [
                "test--cdn-dummy1"
            ],
            "subdomains-without-dns": [],
            "origins": {},
            "compress": True,
            "cookies": [],
            "certificate_id": "AAAA...",
            "headers": [],
            "errors": None,
            "default-ttl": 300,
        }
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1', 'ExtDNS'])
        self.assertEqual(delta_plus['Outputs'].keys(), ['DomainName'])

    def test_template_delta_does_not_include_cloudfront_if_there_are_no_modifications(self):
        context = self._base_context('project-with-cloudfront-minimal')
        (delta_plus, delta_minus) = cfngen.template_delta('project-with-cloudfront-minimal', context)
        self.assertEqual(delta_plus['Resources'].keys(), [])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_does_not_normally_include_ec2(self):
        "we do not want to mess with running VMs"
        context = self._base_context()
        context['ec2']['cluster_size'] = 2
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), [])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_ec2_instance_type(self):
        "we accept to reboot VMs if an instance type change is requested"
        context = self._base_context()
        context['ec2']['type'] = 't2.xlarge'
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['EC2Instance1'])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_does_not_include_ec2_immutable_properties_like_image(self):
        "we don't want random reboot or recreations of instances"
        context = self._base_context()
        context['ec2']['ami'] = 'ami-1234567'
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), [])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_ec2_security_group(self):
        "it's useful to open and close ports"
        context = self._base_context()
        context['project']['aws']['ports'] = [110]
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['StackSecurityGroup'])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_parts_of_cloudfront(self):
        "we want to update CDNs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cloudfront-minimal')
        context['cloudfront']['subdomains'] = [
            "custom-subdomain"
        ]
        (delta_plus, delta_minus) = cfngen.template_delta('project-with-cloudfront-minimal', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['CloudFrontCDN', 'CloudFrontCDNDNS1'])
        self.assertEqual(delta_plus['Resources']['CloudFrontCDNDNS1']['Properties']['Name'], 'custom-subdomain.example.org.')
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_parts_of_elb(self):
        "we want to update ELBs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cluster')
        context['elb']['healthcheck']['protocol'] = 'tcp'
        (delta_plus, delta_minus) = cfngen.template_delta('project-with-cluster', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['ElasticLoadBalancer'])
        self.assertEqual(delta_plus['Resources']['ElasticLoadBalancer']['Properties']['HealthCheck']['Target'], 'TCP:80')
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_elb_security_group(self):
        "for consistency with EC2 security groups"
        context = self._base_context('project-with-cluster')
        context['elb']['protocol'] = 'https'
        context['elb']['certificate'] = 'DUMMY_CERTIFICATE'
        (delta_plus, delta_minus) = cfngen.template_delta('project-with-cluster', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['ElasticLoadBalancer', 'ELBSecurityGroup'])
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_new_external_volumes(self):
        "we want to add additional volumes to projects that are getting their main volume filled"
        context = self._base_context()
        context['ext'] = {
            'size': 10,
            'device': '/dev/sdh',
        }
        (delta_plus, delta_minus) = cfngen.template_delta('dummy1', context)
        self.assertEqual(delta_plus['Resources'].keys(), ['MountPoint1', 'ExtraStorage1'])
        self.assertEqual(delta_plus['Resources']['ExtraStorage1']['Properties']['Size'], '10')
        self.assertEqual(delta_plus['Resources']['MountPoint1']['Properties']['Device'], '/dev/sdh')
        self.assertEqual(delta_plus['Outputs'].keys(), [])

    def test_template_delta_includes_removal_of_subdomains(self):
        context = self._base_context('dummy2')
        context['subdomains'] = []
        (delta_plus, delta_minus) = cfngen.template_delta('dummy2', context)
        self.assertEqual(delta_minus['Resources'].keys(), ['CnameDNS1'])
        self.assertEqual(delta_minus['Outputs'].keys(), [])

    def test_apply_delta_may_add_and_remove_resources(self):
        template = {
            'Resources': {
                'A': 1,
                'B': 2,
            }
        }
        cfngen.apply_delta(template, delta_plus={'Resources': {'C': 3}}, delta_minus={'Resources': {'B': 2}})
        self.assertEqual(template, {'Resources': {'A': 1, 'C': 3}})

    def _base_context(self, project_name='dummy1'):
        stackname = '%s--test' % project_name
        context = cfngen.build_context(project_name, stackname=stackname)
        context_handler.write_context(stackname, context)
        template = cfngen.render_template(context)
        cfngen.write_template(stackname, template)
        return context
