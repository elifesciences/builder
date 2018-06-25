import pytest
from . import base
from buildercore import core, cfngen, context_handler, cloudformation

import logging
LOG = logging.getLogger(__name__)

class TestBuildercoreCfngen():
    # note: this requires pytest, but provides great introspection
    # on which project_name is failing
    @pytest.mark.parametrize("project_name", base.test_projects())
    def test_quick_rendering(self, project_name):
        cfngen.quick_render(project_name)

class TestBuildContext(base.BaseCase):
    def test_existing_alt_config(self):
        stackname = 'dummy2--test'
        more_context = {
            'stackname': stackname,
            'alt-config': 'alt-config1',
        }
        context = cfngen.build_context('dummy2', **more_context)
        self.assertEqual(context['alt-config'], 'alt-config1')
        self.assertEqual(context['ec2']['ami'], 'ami-22222')

    def test_not_existing_alt_config(self):
        stackname = 'dummy2--test'
        more_context = {
            'stackname': stackname,
            'alt-config': 'my-custom-adhoc-instance',
        }
        context = cfngen.build_context('dummy2', **more_context)
        self.assertEqual(context['alt-config'], 'my-custom-adhoc-instance')
        self.assertEqual(context['ec2']['ami'], 'ami-111111')

class TestUpdates(base.BaseCase):
    def test_empty_template_delta(self):
        context = self._base_context()
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(delta_plus, {'Outputs': {}, 'Resources': {}})

    def test_template_delta_includes_cloudfront(self):
        "we can add CDNs (that takes an hour or more) without downtime"
        context = self._base_context()
        stackname, environment_name = core.parse_stackname(context['stackname'])
        context['full_hostname'] = "test--dummy1.example.org"
        context['cloudfront'] = {
            "subdomains": [
                "test--cdn-dummy1.example.org"
            ],
            "subdomains-without-dns": [],
            "origins": {},
            "compress": True,
            "cookies": [],
            "certificate_id": "AAAA...",
            "headers": [],
            "errors": None,
            "default-ttl": 300,
            "logging": False,
        }
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertCountEqual(list(delta_plus['Resources'].keys()), ['CloudFrontCDN', 'CloudFrontCDNDNS1', 'ExtDNS'])
        self.assertEqual(list(delta_plus['Outputs'].keys()), ['DomainName'])

    def test_template_delta_does_not_include_cloudfront_if_there_are_no_modifications(self):
        context = self._base_context('project-with-cloudfront-minimal')
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_plus['Resources'].keys()), [])
        self.assertEqual(list(delta_plus['Outputs'].keys()), [])

    def test_template_delta_does_not_normally_include_ec2(self):
        "we do not want to mess with running VMs"
        context = self._base_context()
        context['ec2']['cluster_size'] = 2
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_plus['Resources'].keys()), [])
        self.assertEqual(list(delta_plus['Outputs'].keys()), [])

    def test_template_delta_includes_ec2_instance_type(self):
        "we accept to reboot VMs if an instance type change is requested"
        context = self._base_context()
        context['ec2']['type'] = 't2.xlarge'
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_edit['Resources'].keys()), ['EC2Instance1'])
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_does_not_include_ec2_immutable_properties_like_image(self):
        "we don't want random reboot or recreations of instances"
        context = self._base_context()
        context['ec2']['ami'] = 'ami-1234567'
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_plus['Resources'].keys()), [])
        self.assertEqual(list(delta_plus['Outputs'].keys()), [])

    def test_template_delta_includes_ec2_security_group(self):
        "it's useful to open and close ports"
        context = self._base_context()
        context['project']['aws']['ports'] = [110]
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_edit['Resources'].keys()), ['StackSecurityGroup'])
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_includes_parts_of_rds(self):
        "we want to update RDS instances in place to avoid data loss"
        context = self._base_context('dummy2')
        context['project']['aws']['rds']['multi-az'] = True
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_edit['Resources'].keys()), ['AttachedDB'])
        self.assertEqual(delta_edit['Resources']['AttachedDB']['Properties']['MultiAZ'], 'true')
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_doesnt_unnecessarily_update_rds(self):
        "we don't want to update RDS instances more than necessary, since it takes time and may cause reboots or replacements"
        context = self._base_context('dummy2')
        updated_context = self._base_context('dummy2', in_memory=False, existing_context=context)
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(updated_context)
        self.assertEqual(list(delta_plus['Resources'].keys()), [])
        self.assertEqual(list(delta_minus['Resources'].keys()), [])
        self.assertEqual(list(delta_plus['Outputs'].keys()), [])
        self.assertEqual(list(delta_minus['Outputs'].keys()), [])

    def test_template_delta_includes_parts_of_cloudfront(self):
        "we want to update CDNs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cloudfront-minimal')
        context['cloudfront']['subdomains'] = [
            "custom-subdomain.example.org"
        ]
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertCountEqual(list(delta_edit['Resources'].keys()), ['CloudFrontCDN', 'CloudFrontCDNDNS1'])
        self.assertEqual(delta_edit['Resources']['CloudFrontCDNDNS1']['Properties']['Name'], 'custom-subdomain.example.org.')
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_includes_parts_of_elb(self):
        "we want to update ELBs in place given how long it takes to recreate them"
        context = self._base_context('project-with-cluster')
        context['elb']['healthcheck']['protocol'] = 'tcp'
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_edit['Resources'].keys()), ['ElasticLoadBalancer'])
        self.assertEqual(delta_edit['Resources']['ElasticLoadBalancer']['Properties']['HealthCheck']['Target'], 'TCP:80')
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_includes_elb_security_group(self):
        "for consistency with EC2 security groups"
        context = self._base_context('project-with-cluster')
        context['elb']['protocol'] = 'https'
        context['elb']['certificate'] = 'DUMMY_CERTIFICATE'
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertCountEqual(list(delta_edit['Resources'].keys()), ['ElasticLoadBalancer', 'ELBSecurityGroup'])
        self.assertEqual(list(delta_edit['Outputs'].keys()), [])

    def test_template_delta_includes_new_external_volumes(self):
        "we want to add additional volumes to projects that are getting their main volume filled"
        context = self._base_context()
        context['ext'] = {
            'size': 10,
            'device': '/dev/sdh',
        }
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertCountEqual(list(delta_plus['Resources'].keys()), ['MountPoint1', 'ExtraStorage1'])
        self.assertEqual(delta_plus['Resources']['ExtraStorage1']['Properties']['Size'], '10')
        self.assertEqual(delta_plus['Resources']['MountPoint1']['Properties']['Device'], '/dev/sdh')
        self.assertCountEqual(list(delta_plus['Outputs'].keys()), [])

    def test_template_delta_includes_removal_of_subdomains(self):
        context = self._base_context('dummy2')
        context['subdomains'] = []
        (delta_plus, delta_edit, delta_minus, cloudformation_delta, new_terraform_template_file) = cfngen.template_delta(context)
        self.assertEqual(list(delta_minus['Resources'].keys()), ['CnameDNS1'])
        self.assertEqual(list(delta_minus['Outputs'].keys()), [])

    def _base_context(self, project_name='dummy1', in_memory=False, existing_context=None):
        environment_name = base.generate_environment_name()
        stackname = '%s--%s' % (project_name, environment_name)
        context = cfngen.build_context(project_name, stackname=stackname, existing_context=existing_context if existing_context is not None else {})
        if not in_memory:
            context_handler.write_context(stackname, context)
            template = cloudformation.render_template(context)
            cloudformation.write_template(stackname, template)
        return context
