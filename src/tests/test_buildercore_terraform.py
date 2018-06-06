import json
import os
import re
import shutil
import yaml
from os.path import exists, join
from mock import patch, MagicMock
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

    @patch('buildercore.terraform.Terraform')
    def test_init_providers(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--prod'
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        terraform_binary.init.assert_called_once()
        for _, configuration in self._load_terraform_file(stackname, 'providers').get('provider').items():
            self.assertIn('version', configuration)

    @patch('buildercore.terraform.Terraform')
    def test_fastly_provider_reads_api_key_from_vault(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--prod'
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        providers_file = self._load_terraform_file(stackname, 'providers')
        self.assertEqual(
            providers_file.get('provider').get('fastly').get('api_key'),
            '${data.vault_generic_secret.fastly.data["api_key"]}'
        )
        self.assertEqual(
            providers_file.get('data').get('vault_generic_secret').get('fastly'),
            {
                'path': 'secret/builder/apikey/fastly',
            }
        )

    @patch('buildercore.terraform.Terraform')
    def test_delta(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        terraform_binary.plan.return_value = (0, 'Plan output: ...', '')
        stackname = 'project-with-fastly-minimal--prod'
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        delta = terraform.generate_delta(context)
        self.assertEqual(delta, terraform.TerraformDelta('Plan output: ...'))

    def test_fastly_template_minimal(self):
        extra = {
            'stackname': 'project-with-fastly-minimal--prod',
        }
        context = cfngen.build_context('project-with-fastly-minimal', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
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
                            'backend': [{
                                'address': 'prod--www.example.org',
                                'name': 'project-with-fastly-minimal--prod',
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': 'prod--www.example.org',
                                'ssl_sni_hostname': 'prod--www.example.org',
                                'ssl_check_cert': True,
                            }],
                            'default_ttl': 3600,
                            'request_setting': [{
                                'name': 'default',
                                'default_host': 'prod--www.example.org',
                                'force_ssl': True,
                                'timer_support': True,
                                'xff': 'leave',
                            }],
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
            template
        )

    def test_fastly_template_complex(self):
        extra = {
            'stackname': 'project-with-fastly-complex--prod',
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'data': {
                    'http': {
                        'error-page-503': {
                            'url': 'https://example.com/'
                        },
                    },
                },
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
                            'backend': [
                                {
                                    'address': 'default.example.org',
                                    'name': 'default',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'default.example.org',
                                    'ssl_sni_hostname': 'default.example.org',
                                    'ssl_check_cert': True,
                                    'healthcheck': 'default',
                                },
                                {
                                    'address': 'prod-special.example.org',
                                    'name': 'articles',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'prod-special.example.org',
                                    'ssl_sni_hostname': 'prod-special.example.org',
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles-condition',
                                    'healthcheck': 'default',
                                }
                            ],
                            'request_setting': [
                                {
                                    'name': 'default',
                                    'default_host': 'default.example.org',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                },
                                {
                                    'name': 'backend-articles-request-settings',
                                    'default_host': 'prod-special.example.org',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles-condition',
                                },
                            ],
                            'default_ttl': 86400,
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
                            'healthcheck': {
                                'host': 'prod--www.example.org',
                                'name': 'default',
                                'path': '/ping-fastly',
                                'check_interval': 30000,
                                'timeout': 10000,
                            },
                            'condition': [
                                {
                                    'name': 'backend-articles-condition',
                                    'statement': 'req.url ~ "^/articles"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'condition-503',
                                    'statement': 'beresp.status == 503',
                                    'type': 'CACHE',
                                },
                                {
                                    'name': 'condition-surrogate-article-id',
                                    'statement': 'req.url ~ "^/articles/(\\d+)/(.+)$"',
                                    'type': 'CACHE',
                                },
                            ],
                            'response_object': [
                                {
                                    'name': 'error-503',
                                    'status': 503,
                                    'response': 'Service Unavailable',
                                    'content': '${data.http.error-page-503.body}',
                                    'content_type': 'text/html; charset=us-ascii',
                                    'cache_condition': 'condition-503',
                                },
                            ],
                            'vcl': [
                                {
                                    'name': 'gzip-by-content-type-suffix',
                                    'content': '${file("gzip-by-content-type-suffix.vcl")}',
                                },
                                {
                                    'name': 'main',
                                    'content': '${file("main.vcl")}',
                                    'main': True,
                                },
                            ],
                            'header': [
                                {
                                    'name': 'surrogate-keys article-id',
                                    'type': 'cache',
                                    'action': 'set',
                                    'source': 'regsub(req.url, "^/articles/(\\d+)/(.+)$", "article/\\1")',
                                    'destination': 'http.surrogate-key',
                                    'ignore_if_set': True,
                                    'cache_condition': 'condition-surrogate-article-id',
                                },
                            ],
                            'force_destroy': True,
                        }
                    }
                },
            },
            template
        )

    def test_fastly_template_gcs_logging(self):
        extra = {
            'stackname': 'project-with-fastly-gcs--prod',
        }
        context = cfngen.build_context('project-with-fastly-gcs', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertIn('gcslogging', service)
        self.assertEqual(service['gcslogging'].get('name'), 'default')
        self.assertEqual(service['gcslogging'].get('bucket_name'), 'my-bucket')
        self.assertEqual(service['gcslogging'].get('path'), 'my-project/')
        self.assertEqual(service['gcslogging'].get('period'), 1800)
        self.assertEqual(service['gcslogging'].get('message_type'), 'blank')
        self.assertEqual(service['gcslogging'].get('email'), '${data.vault_generic_secret.fastly-gcs-logging.data["email"]}')
        self.assertEqual(service['gcslogging'].get('secret_key'), '${data.vault_generic_secret.fastly-gcs-logging.data["secret_key"]}')

        log_format = service['gcslogging'].get('format')
        # the non-rendered log_format is not even valid JSON
        self.assertIsNotNone(log_format)
        self.assertRegex(log_format, "\{.*\}")

        data = template['data']['vault_generic_secret']['fastly-gcs-logging']
        self.assertEqual(data, {'path': 'secret/builder/apikey/fastly-gcs-logging'})

    def test_gcp_template(self):
        extra = {
            'stackname': 'project-on-gcp--prod',
        }
        context = cfngen.build_context('project-on-gcp', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['google_storage_bucket']['widgets-prod']
        self.assertEqual(service, {
            'name': 'widgets-prod',
            'location': 'us-east4',
            'storage_class': 'REGIONAL',
            'project': 'elife-something',
        })

    def test_sanity_of_rendered_log_format(self):
        def _render_log_format_with_dummy_template():
            return re.sub(
                r"%\{.+\}(V|t)",
                '42',
                terraform.FASTLY_LOG_FORMAT,
            )
        log_sample = json.loads(_render_log_format_with_dummy_template())
        self.assertEqual(log_sample.get('object_hits'), 42)
        self.assertEqual(log_sample.get('geo_city'), '42')

    def test_generated_template_file_storage(self):
        contents = '{"key":"value"}'
        filename = terraform.write_template('dummy1--test', contents)
        self.assertEqual(filename, '.cfn/terraform/dummy1--test/generated.tf.json')
        self.assertEqual(terraform.read_template('dummy1--test'), contents)

    def _parse_template(self, terraform_template):
        """use yaml module to load JSON to avoid large u'foo' vs 'foo' string diffs
        https://stackoverflow.com/a/16373377/91590"""
        return yaml.safe_load(terraform_template)

    def _load_terraform_file(self, stackname, filename):
        with open(join(terraform.TERRAFORM_DIR, stackname, '%s.tf.json' % filename), 'r') as fp:
            return self._parse_template(fp.read())
