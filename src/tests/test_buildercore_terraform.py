import json
import os
import re
import shutil
import yaml
from os.path import exists, join
from . import base
from buildercore import cfngen, terraform

class TestBuildercoreTerraform(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        os.environ['LOGNAME'] = 'my_user'
        test_directory = join(terraform.TERRAFORM_DIR, 'dummy1--test')
        if exists(test_directory):
            shutil.rmtree(test_directory)

    def tearDown(self):
        del os.environ['LOGNAME']

    def test_fastly_template_minimal(self):
        extra = {
            'stackname': 'project-with-fastly-minimal--prod',
        }
        context = cfngen.build_context('project-with-fastly-minimal', **extra)
        terraform_template = terraform.render(context)
        data = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-minimal--prod',
                            'domain': [{
                                'name': 'prod--cdn-of-www.example.org'
                            }],
                            'backend': {
                                'address': 'prod--www.example.org',
                                'name': 'project-with-fastly-minimal--prod',
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': 'prod--www.example.org',
                                'ssl_check_cert': True,
                            },
                            'request_setting': {
                                'name': 'default',
                                'force_ssl': True,
                                'timer_support': True,
                                'xff': 'leave',
                            },
                            'gzip': {
                                'name': 'default',
                                'content_types': ['application/javascript', 'application/json',
                                                  'application/vnd.ms-fontobject',
                                                  'application/x-font-opentype',
                                                  'application/x-font-truetype',
                                                  'application/x-font-ttf',
                                                  'application/x-javascript', 'application/xml',
                                                  'font/eot', 'font/opentype', 'font/otf',
                                                  'image/svg+xml', 'image/vnd.microsoft.icon',
                                                  'text/css', 'text/html', 'text/javascript',
                                                  'text/plain', 'text/xml'],
                                'extensions': ['css', 'eot', 'html', 'ico', 'js', 'json', 'otf',
                                               'ttf'],
                            },
                            'force_destroy': True
                        }
                    }
                },
            },
            data
        )

    def test_fastly_template_complex(self):
        extra = {
            'stackname': 'project-with-fastly-complex--prod',
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        terraform_template = terraform.render(context)
        data = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-complex--prod',
                            'domain': [
                                {
                                    'name': 'prod--cdn1-of-www.example.org'
                                },
                                {
                                    'name': 'prod--cdn2-of-www.example.org'
                                },
                                {
                                    'name': 'future.example.org'
                                },
                            ],
                            'backend': {
                                'address': 'prod--www.example.org',
                                'name': 'project-with-fastly-complex--prod',
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': 'prod--www.example.org',
                                'ssl_check_cert': True
                            },
                            'request_setting': {
                                'name': 'default',
                                'force_ssl': True,
                                'timer_support': True,
                                'xff': 'leave',
                            },
                            'gzip': {
                                'name': 'default',
                                'content_types': ['application/javascript', 'application/json',
                                                  'application/vnd.ms-fontobject',
                                                  'application/x-font-opentype',
                                                  'application/x-font-truetype',
                                                  'application/x-font-ttf',
                                                  'application/x-javascript', 'application/xml',
                                                  'font/eot', 'font/opentype', 'font/otf',
                                                  'image/svg+xml', 'image/vnd.microsoft.icon',
                                                  'text/css', 'text/html', 'text/javascript',
                                                  'text/plain', 'text/xml'],
                                'extensions': ['css', 'eot', 'html', 'ico', 'js', 'json', 'otf',
                                               'ttf'],
                            },
                            'force_destroy': True
                        }
                    }
                },
            },
            data
        )

    def test_fastly_template_gcs_logging(self):
        extra = {
            'stackname': 'project-with-fastly-gcs--prod',
        }
        context = cfngen.build_context('project-with-fastly-gcs', **extra)
        terraform_template = terraform.render(context)
        data = self._parse_template(terraform_template)
        service = data['resource']['fastly_service_v1']['fastly-cdn']
        self.assertIn('gcslogging', service)
        self.assertEqual(service['gcslogging'].get('name'), 'default')
        self.assertEqual(service['gcslogging'].get('bucket_name'), 'my-bucket')
        self.assertEqual(service['gcslogging'].get('path'), 'my-project/')
        self.assertEqual(service['gcslogging'].get('period'), 1800)
        self.assertEqual(service['gcslogging'].get('message_type'), 'blank')

        log_format = service['gcslogging'].get('format')
        # the non-rendered log_format is not even valid JSON
        self.assertIsNotNone(log_format)
        self.assertRegex(log_format, "\{.*\}")

    def test_sanity_of_rendered_log_format(self):
        def _render_log_format_with_dummy_data():
            return re.sub(
                r"%\{.+\}(V|t)", 
                '42',
                terraform.FASTLY_LOG_FORMAT,
            )
        log_sample = json.loads(_render_log_format_with_dummy_data())
        self.assertEqual(log_sample.get('object_hits'), 42)
        self.assertEqual(log_sample.get('geo_city'), '42')


    def test_generated_template_file_storage(self):
        contents = '{"key":"value"}'
        terraform.write_template('dummy1--test', contents)
        self.assertEqual(terraform.read_template('dummy1--test'), contents)

    def _parse_template(self, terraform_template):
        """use yaml module to load JSON to avoid large u'foo' vs 'foo' string diffs
        https://stackoverflow.com/a/16373377/91590"""
        return yaml.safe_load(terraform_template)
