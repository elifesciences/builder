from collections import OrderedDict
import json
import os
import re
import shutil
import yaml
from os.path import exists, join
from mock import patch, MagicMock
# pylint: disable-msg=import-error
from unittest2 import TestCase
from . import base
from buildercore import cfngen, terraform


class TestTerraformTemplate(TestCase):
    def test_resource_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', block={
            'location': 'EU',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', {'location': 'EU'}),
                    ])),
                ])
            }
        )

    def test_nested_resource_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('labels', {'project': 'journal'}),
                        ])),
                    ])),
                ])
            }
        )

    def test_nested_resource_creation_if_already_existing(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        overwrite = lambda: template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={'project': 'lax', })
        self.assertRaises(terraform.TerraformTemplateError, overwrite)

    def test_resource_creation_in_multiple_phases(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', block={
            'location': 'EU',
        })
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('location', 'EU'),
                            ('labels', {'project': 'journal'}),
                        ])),
                    ])),
                ])
            }
        )

    def test_resource_elements_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource_element('google_bigquery_dataset', 'my_dataset', key='access', block={
            'role': 'reader',
        })
        template.populate_resource_element('google_bigquery_dataset', 'my_dataset', key='access', block={
            'role': 'writer',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('access', [
                                {'role': 'reader'},
                                {'role': 'writer'},
                            ]),
                        ])),
                    ])),
                ])
            }
        )

    def test_data_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', OrderedDict([
                            ('username', 'mickey'),
                            ('password', 'mouse'),
                        ])),
                    ])),
                ])
            }
        )

    def test_data_creation_same_type(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        template.populate_data('vault_generic_secret', 'my_ssh_key', block={
            'private': '-----BEGIN RSA PRIVATE KEY-----',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', {
                            'username': 'mickey',
                            'password': 'mouse',
                        }),
                        ('my_ssh_key', {
                            'private': '-----BEGIN RSA PRIVATE KEY-----',
                        }),
                    ])),
                ])
            }
        )

    def test_data_creation_different_type(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        template.populate_data('http', 'my_page', block={
            'url': 'https://example.com',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', {
                            'username': 'mickey',
                            'password': 'mouse',
                        }),
                    ])),
                    ('http', OrderedDict([
                        ('my_page', {
                            'url': 'https://example.com',
                        }),
                    ])),
                ])
            }
        )

    def test_data_creation_if_already_existing(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
        })
        overwrite = lambda: template.populate_data('vault_generic_secret', 'my_credentials', block={'username': 'minnie'})
        self.assertRaises(terraform.TerraformTemplateError, overwrite)

    def test_local_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_local('answer', 42)
        template.populate_local('incorrect', 43)
        self.assertEqual(
            template.to_dict(),
            {
                'locals': OrderedDict([
                    ('answer', 42),
                    ('incorrect', 43),
                ])
            }
        )


class TestBuildercoreTerraform(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        os.environ['LOGNAME'] = 'my_user'
        self.environment = base.generate_environment_name()
        test_directory = join(terraform.TERRAFORM_DIR, 'dummy1--%s' % self.environment)
        if exists(test_directory):
            shutil.rmtree(test_directory)

    def tearDown(self):
        del os.environ['LOGNAME']

    @patch('buildercore.terraform.Terraform')
    def test_init_providers(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--%s' % self.environment
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        terraform_binary.init.assert_called_once()
        for _, configuration in self._load_terraform_file(stackname, 'providers').get('provider').items():
            self.assertIn('version', configuration)

    @patch('buildercore.terraform.Terraform')
    def test_fastly_provider_reads_api_key_from_vault(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--%s' % self.environment
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
        stackname = 'project-with-fastly-minimal--%s' % self.environment
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        delta = terraform.generate_delta(context)
        self.assertEqual(delta, terraform.TerraformDelta('Plan output: ...'))

    def test_fastly_template_minimal(self):
        extra = {
            'stackname': 'project-with-fastly-minimal--%s' % self.environment,
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
                            'name': 'project-with-fastly-minimal--%s' % self.environment,
                            'domain': [{
                                'name': '%s--cdn-of-www.example.org' % self.environment,
                            }],
                            'backend': [{
                                'address': '%s--www.example.org' % self.environment,
                                'name': 'project-with-fastly-minimal--%s' % self.environment,
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': '%s--www.example.org' % self.environment,
                                'ssl_sni_hostname': '%s--www.example.org' % self.environment,
                                'ssl_check_cert': True,
                            }],
                            'default_ttl': 3600,
                            'request_setting': [
                                {
                                    'name': 'force-ssl',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                }
                            ],
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
                            'force_destroy': True,
                            'vcl': [],
                        }
                    }
                },
            },
            template
        )

    def test_fastly_template_complex(self):
        extra = {
            'stackname': 'project-with-fastly-complex--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'data': {
                    'http': {
                        'error-page-404': {
                            'url': 'https://example.com/404.html'
                        },
                        'error-page-503': {
                            'url': 'https://example.com/503.html'
                        },
                        'error-page-4xx': {
                            'url': 'https://example.com/4xx.html'
                        },
                        'error-page-5xx': {
                            'url': 'https://example.com/5xx.html'
                        },
                    },
                    'template_file': {
                        'error-page-vcl-503': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status == 503',
                                'synthetic_response': '${data.http.error-page-503.body}',
                            },
                        },
                        'error-page-vcl-404': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status == 404',
                                'synthetic_response': '${data.http.error-page-404.body}',
                            },
                        },
                        'error-page-vcl-4xx': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status >= 400 && obj.status <= 499',
                                'synthetic_response': '${data.http.error-page-4xx.body}',
                            },
                        },
                        'error-page-vcl-5xx': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status >= 500 && obj.status <= 599',
                                'synthetic_response': '${data.http.error-page-5xx.body}',
                            },
                        },
                        'journal-submit': {
                            'template': '${file("journal-submit.vcl.tpl")}',
                            'vars': {
                                'percentage': 10,
                                'referer': '^https://xpub\.example\.com/',
                                'xpub_uri': 'https://xpub.example.com/login',
                            },
                        },
                    },
                },
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-complex--%s' % self.environment,
                            'domain': [
                                {
                                    'name': '%s--cdn1-of-www.example.org' % self.environment,
                                },
                                {
                                    'name': '%s--cdn2-of-www.example.org' % self.environment,
                                },
                                {
                                    'name': 'example.org'
                                },
                                {
                                    'name': 'anotherdomain.org'
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
                                    'address': '%s-special.example.org' % self.environment,
                                    'name': 'articles',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles-condition',
                                    'healthcheck': 'default',
                                    'shield': 'amsterdam-nl',
                                },
                                {
                                    'address': '%s-special2.example.org' % self.environment,
                                    'name': 'articles2',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special2.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special2.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles2-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
                                },
                                {
                                    'address': '%s-special3.example.org' % self.environment,
                                    'name': 'articles3',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special3.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special3.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles3-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
                                },
                            ],
                            'acl': [
                                {
                                    'name': 'ip_blacklist',
                                },
                            ],
                            'request_setting': [
                                {
                                    'name': 'force-ssl',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                },
                                {
                                    'name': 'backend-articles-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles-condition',
                                },
                                {
                                    'name': 'backend-articles2-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles2-condition',
                                },
                                {
                                    'name': 'backend-articles3-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles3-condition',
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
                                'host': '%s--www.example.org' % self.environment,
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
                                    'name': 'backend-articles2-condition',
                                    'statement': 'req.url ~ "^/articles2"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'backend-articles3-condition',
                                    'statement': 'req.url ~ "^/articles3"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'ip-blacklist',
                                    'statement': 'client.ip ~ ip_blacklist',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'condition-surrogate-article-id',
                                    'statement': 'req.url ~ "^/articles/(\\d+)/(.+)$"',
                                    'type': 'CACHE',
                                },
                            ],
                            'response_object': [
                                {
                                    'name': 'ip-blacklist',
                                    'request_condition': 'ip-blacklist',
                                    'status': 403,
                                    'response': 'Forbidden',
                                },
                            ],
                            'vcl': [
                                {
                                    'name': 'gzip-by-content-type-suffix',
                                    'content': '${file("gzip-by-content-type-suffix.vcl")}',
                                },
                                {
                                    'name': 'journal-submit',
                                    'content': '${data.template_file.journal-submit.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-503',
                                    'content': '${data.template_file.error-page-vcl-503.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-404',
                                    'content': '${data.template_file.error-page-vcl-404.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-4xx',
                                    'content': '${data.template_file.error-page-vcl-4xx.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-5xx',
                                    'content': '${data.template_file.error-page-vcl-5xx.rendered}',
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

    def test_fastly_template_shield(self):
        extra = {
            'stackname': 'project-with-fastly-shield--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'dca-dc-us')
        self.assertIn('domain', service)

    def test_fastly_template_shield_pop(self):
        extra = {
            'stackname': 'project-with-fastly-shield-pop--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield-pop', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'london-uk')
        self.assertIn('domain', service)

    def test_fastly_template_shield_aws_region(self):
        base.switch_in_test_settings(['src/tests/fixtures/additional-projects/'])
        extra = {
            'stackname': 'project-with-fastly-shield-aws-region--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield-aws-region', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'frankfurt-de')

    def test_fastly_template_gcs_logging(self):
        extra = {
            'stackname': 'project-with-fastly-gcs--%s' % self.environment,
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

    def test_fastly_template_bigquery_logging(self):
        extra = {
            'stackname': 'project-with-fastly-bigquery--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-bigquery', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertIn('bigquerylogging', service)
        self.assertEqual(service['bigquerylogging'].get('name'), 'bigquery')
        self.assertEqual(service['bigquerylogging'].get('project_id'), 'my-project')
        self.assertEqual(service['bigquerylogging'].get('dataset'), 'my_dataset')
        self.assertEqual(service['bigquerylogging'].get('table'), 'my_table')
        self.assertEqual(service['bigquerylogging'].get('email'), '${data.vault_generic_secret.fastly-gcp-logging.data["email"]}')
        self.assertEqual(service['bigquerylogging'].get('secret_key'), '${data.vault_generic_secret.fastly-gcp-logging.data["secret_key"]}')

        log_format = service['bigquerylogging'].get('format')
        # the non-rendered log_format is not even valid JSON
        self.assertIsNotNone(log_format)
        self.assertRegex(log_format, "\{.*\}")

        data = template['data']['vault_generic_secret']['fastly-gcp-logging']
        self.assertEqual(data, {'path': 'secret/builder/apikey/fastly-gcp-logging'})

    def test_gcp_template(self):
        extra = {
            'stackname': 'project-on-gcp--%s' % self.environment,
        }
        context = cfngen.build_context('project-on-gcp', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        bucket = template['resource']['google_storage_bucket']['widgets-%s' % self.environment]
        self.assertEqual(bucket, {
            'name': 'widgets-%s' % self.environment,
            'location': 'us-east4',
            'storage_class': 'REGIONAL',
            'project': 'elife-something',
        })

    def test_bigquery_datasets_only(self):
        extra = {
            'stackname': 'project-with-bigquery-datasets-only--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-bigquery-datasets-only', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_%s' % self.environment]
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_%s' % self.environment,
            'project': 'elife-something',
        })

        self.assertNotIn('google_bigquery_table', template['resource'])

    def test_bigquery_full_template(self):
        extra = {
            'stackname': 'project-with-bigquery--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-bigquery', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_%s' % self.environment]
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_%s' % self.environment,
            'project': 'elife-something',
        })

        table = template['resource']['google_bigquery_table']['my_dataset_%s_widgets' % self.environment]
        self.assertEqual(table, {
            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
            'table_id': 'widgets',
            'project': 'elife-something',
            'schema': '${file("key-value.json")}',
        })

        table = template['resource']['google_bigquery_table']['my_dataset_%s_partitioned_table' % self.environment]
        self.assertEqual(table, {
            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
            'table_id': 'partitioned_table',
            'project': 'elife-something',
            'schema': '${file("key-value.json")}',
            'time_partitioning': {
                'field': 'a_timestamp',
                'type': 'DAY',
            },
        })

    def test_bigquery_remote_paths(self):
        "remote paths require terraform to fetch and load the files, which requires another entry in the 'data' list"
        pname = 'project-with-bigquery-remote-schemas'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertEqual(
            terraform_template,
            {
                'resource': {
                    'google_bigquery_dataset': {
                        'my_dataset_%s' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': 'my_dataset_%s' % self.environment
                        }
                    },
                    'google_bigquery_table': {
                        'my_dataset_%s_remote' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'remote',
                            'schema': '${data.http.my_dataset_%s_remote.body}' % self.environment,
                        },
                        'my_dataset_%s_remote_github' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'remote_github',
                            'schema': '${data.http.my_dataset_%s_remote_github.body}' % self.environment,
                        },
                        'my_dataset_%s_local' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'local',
                            'schema': '${file("key-value.json")}'
                        }
                    }
                },
                'data': {
                    'http': {
                        'my_dataset_%s_remote' % self.environment: {
                            'url': 'https://example.org/schemas/remote.json'
                        },
                        'my_dataset_%s_remote_github' % self.environment: {
                            'url': 'https://raw.githubusercontent.com/myrepo/something.json',
                            'request_headers': {
                                'Authorization': 'token ${data.vault_generic_secret.github.data["token"]}',
                            },
                        },
                    },
                    'vault_generic_secret': {
                        'github': {'path': 'secret/builder/apikey/github'}
                    },
                }
            }
        )

    @patch('buildercore.terraform.Terraform')
    def test_kubernetes_provider(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-eks--%s' % self.environment
        context = cfngen.build_context('project-with-eks', stackname=stackname)
        terraform.init(stackname, context)
        providers = self._load_terraform_file(stackname, 'providers')
        self.assertIn('kubernetes', providers['provider'].keys())
        self.assertEqual(
            {
                'version': "= %s" % '1.5.2',
                'host': '${data.aws_eks_cluster.main.endpoint}',
                'cluster_ca_certificate': '${base64decode(data.aws_eks_cluster.main.certificate_authority.0.data)}',
                'token': '${data.aws_eks_cluster_auth.main.token}',
                'load_config_file': False,
            },
            providers['provider']['kubernetes']
        )
        self.assertIn('aws_eks_cluster', providers['data'])
        self.assertEqual(
            {
                'main': {
                    'name': '${aws_eks_cluster.main.name}',
                },
            },
            providers['data']['aws_eks_cluster']
        )
        self.assertIn('aws_eks_cluster_auth', providers['data'])
        self.assertEqual(
            {
                'main': {
                    'name': '${aws_eks_cluster.main.name}',
                },
            },
            providers['data']['aws_eks_cluster_auth']
        )

    def test_eks_cluster(self):
        pname = 'project-with-eks'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertIn('resource', terraform_template.keys())
        self.assertIn('aws_eks_cluster', terraform_template['resource'].keys())
        self.assertIn('aws_iam_role', terraform_template['resource'].keys())
        self.assertIn('aws_security_group', terraform_template['resource'].keys())
        self.assertIn('aws_iam_instance_profile', terraform_template['resource'].keys())
        self.assertIn('aws_security_group_rule', terraform_template['resource'].keys())
        self.assertIn('aws_iam_role_policy_attachment', terraform_template['resource'].keys())
        self.assertIn('aws_launch_configuration', terraform_template['resource'].keys())
        self.assertIn('aws_autoscaling_group', terraform_template['resource'].keys())
        self.assertIn('kubernetes_config_map', terraform_template['resource'].keys())
        self.assertIn('data', terraform_template.keys())
        self.assertIn('aws_ami', terraform_template['data'].keys())

        self.assertIn('main', terraform_template['resource']['aws_eks_cluster'])
        self.assertEqual(
            terraform_template['resource']['aws_eks_cluster']['main'],
            {
                'name': 'project-with-eks--%s' % self.environment,
                'version': '1.11',
                'role_arn': '${aws_iam_role.master.arn}',
                'vpc_config': {
                    'security_group_ids': ['${aws_security_group.master.id}'],
                    'subnet_ids': ['subnet-a1a1a1a1', 'subnet-b2b2b2b2'],
                },
                'depends_on': [
                    "aws_iam_role_policy_attachment.master_kubernetes",
                    "aws_iam_role_policy_attachment.master_ecs",
                ]
            }
        )

        self.assertIn('master', terraform_template['resource']['aws_iam_role'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role']['master']['name'],
            'project-with-eks--%s--AmazonEKSMasterRole' % self.environment
        )
        self.assertEqual(
            json.loads(terraform_template['resource']['aws_iam_role']['master']['assume_role_policy']),
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "eks.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        )

        self.assertIn('master_kubernetes', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role_policy_attachment']['master_kubernetes'],
            {
                'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
                'role': "${aws_iam_role.master.name}",
            }
        )
        self.assertIn('master_ecs', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role_policy_attachment']['master_ecs'],
            {
                'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
                'role': "${aws_iam_role.master.name}",
            }
        )

        self.assertIn('master', terraform_template['resource']['aws_security_group'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group']['master'],
            {
                'name': 'project-with-eks--%s--master' % self.environment,
                'description': 'Cluster communication with worker nodes',
                'vpc_id': 'vpc-78a2071d',
                'egress': {
                    'from_port': 0,
                    'to_port': 0,
                    'protocol': '-1',
                    'cidr_blocks': ['0.0.0.0/0'],
                },
                'tags': {
                    'Project': 'project-with-eks',
                    'Environment': self.environment,
                    'Name': 'project-with-eks--%s' % self.environment,
                    'Cluster': 'project-with-eks--%s' % self.environment,
                }
            }
        )

        self.assertIn('worker_to_master', terraform_template['resource']['aws_security_group_rule'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group_rule']['worker_to_master'],
            {
                'description': 'Allow pods to communicate with the cluster API Server',
                'from_port': 443,
                'protocol': 'tcp',
                'security_group_id': '${aws_security_group.master.id}',
                'source_security_group_id': '${aws_security_group.worker.id}',
                'to_port': 443,
                'type': 'ingress',
            }
        )

        self.assertIn('worker', terraform_template['resource']['aws_security_group'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group']['worker'],
            {
                'name': 'project-with-eks--%s--worker' % self.environment,
                'description': 'Security group for all worker nodes in the cluster',
                'vpc_id': 'vpc-78a2071d',
                'egress': {
                    'from_port': 0,
                    'to_port': 0,
                    'protocol': '-1',
                    'cidr_blocks': ['0.0.0.0/0'],
                },
                'tags': {
                    'Project': 'project-with-eks',
                    'Environment': self.environment,
                    'Name': 'project-with-eks--%s' % self.environment,
                    'Cluster': 'project-with-eks--%s' % self.environment,
                    'kubernetes.io/cluster/%s': 'owned',
                }
            }
        )

        self.assertIn('worker_to_worker', terraform_template['resource']['aws_security_group_rule'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group_rule']['worker_to_worker'],
            {
                'description': 'Allow worker nodes to communicate with each other',
                'from_port': 0,
                'protocol': '-1',
                'security_group_id': '${aws_security_group.worker.id}',
                'source_security_group_id': '${aws_security_group.worker.id}',
                'to_port': 65535,
                'type': 'ingress',
            }
        )

        self.assertIn('master_to_worker', terraform_template['resource']['aws_security_group_rule'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group_rule']['master_to_worker'],
            {
                'description': 'Allow worker Kubelets and pods to receive communication from the cluster control plane',
                'from_port': 1025,
                'protocol': 'tcp',
                'security_group_id': '${aws_security_group.worker.id}',
                'source_security_group_id': '${aws_security_group.master.id}',
                'to_port': 65535,
                'type': 'ingress',
            }
        )

        self.assertIn('eks_public_to_worker', terraform_template['resource']['aws_security_group_rule'])
        self.assertEqual(
            terraform_template['resource']['aws_security_group_rule']['eks_public_to_worker'],
            {
                'description': "Allow worker to expose NodePort services",
                'from_port': 30000,
                'protocol': 'tcp',
                'security_group_id': '${aws_security_group.worker.id}',
                'to_port': 32767,
                'cidr_blocks': ["0.0.0.0/0"],
                'type': 'ingress',
            }
        )

        self.assertIn('worker', terraform_template['resource']['aws_iam_role'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role']['worker']['name'],
            'project-with-eks--%s--AmazonEKSWorkerRole' % self.environment
        )
        self.assertEqual(
            json.loads(terraform_template['resource']['aws_iam_role']['worker']['assume_role_policy']),
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "ec2.amazonaws.com",
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        )

        self.assertIn('worker_connect', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role_policy_attachment']['worker_connect'],
            {
                'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
                'role': "${aws_iam_role.worker.name}",
            }
        )

        self.assertIn('worker_cni', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role_policy_attachment']['worker_cni'],
            {
                'policy_arn': "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
                'role': "${aws_iam_role.worker.name}",
            }
        )

        self.assertIn('worker_ecr', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role_policy_attachment']['worker_ecr'],
            {
                'policy_arn': "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
                'role': "${aws_iam_role.worker.name}",
            }
        )

        self.assertIn('worker', terraform_template['resource']['aws_iam_instance_profile'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_instance_profile']['worker'],
            {
                'name': 'project-with-eks--%s--worker' % self.environment,
                'role': '${aws_iam_role.worker.name}'
            }
        )

        self.assertIn('worker', terraform_template['data']['aws_ami'])
        self.assertEqual(
            terraform_template['data']['aws_ami']['worker'],
            {
                'filter': {
                    'name': 'name',
                    'values': ['amazon-eks-node-1.11-v*'],
                },
                'most_recent': True,
                'owners': ['602401143452'],
            }
        )

        self.assertIn('worker_userdata', terraform_template['locals'])
        self.assertIn('/bin/bash', terraform_template['locals']['worker_userdata'])

        self.assertIn('worker', terraform_template['resource']['aws_launch_configuration'])
        self.assertEqual(
            terraform_template['resource']['aws_launch_configuration']['worker'],
            {
                'associate_public_ip_address': True,
                'iam_instance_profile': '${aws_iam_instance_profile.worker.name}',
                'image_id': '${data.aws_ami.worker.id}',
                'instance_type': 't2.small',
                'name_prefix': 'project-with-eks--%s--worker' % self.environment,
                'security_groups': ['${aws_security_group.worker.id}'],
                'user_data_base64': '${base64encode(local.worker_userdata)}',
                'lifecycle': {
                    'create_before_destroy': True,
                },
            }
        )

        self.assertIn('worker', terraform_template['resource']['aws_autoscaling_group'])
        self.assertEqual(
            terraform_template['resource']['aws_autoscaling_group']['worker'],
            {
                'name': "project-with-eks--%s--worker" % self.environment,
                'launch_configuration': "${aws_launch_configuration.worker.id}",
                'min_size': 1,
                'max_size': 3,
                'desired_capacity': 3,
                'vpc_zone_identifier': ['subnet-a1a1a1a1', 'subnet-b2b2b2b2'],
                'tags': [
                    {
                        'key': 'Project',
                        'value': 'project-with-eks',
                        'propagate_at_launch': True,
                    },
                    {
                        'key': 'Environment',
                        'value': self.environment,
                        'propagate_at_launch': True,
                    },
                    {
                        'key': 'Name',
                        'value': 'project-with-eks--%s' % self.environment,
                        'propagate_at_launch': True,
                    },
                    {
                        'key': 'Cluster',
                        'value': 'project-with-eks--%s' % self.environment,
                        'propagate_at_launch': True,
                    },
                    {
                        'key': 'kubernetes.io/cluster/project-with-eks--%s' % self.environment,
                        'value': 'owned',
                        'propagate_at_launch': True,
                    },
                ],
            }
        )

        self.assertIn('user', terraform_template['resource']['aws_iam_role'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role']['user']['name'],
            'project-with-eks--%s--AmazonEKSUserRole' % self.environment
        )
        self.assertEqual(
            json.loads(terraform_template['resource']['aws_iam_role']['user']['assume_role_policy']),
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            'AWS': 'arn:aws:iam::512686554592:root',
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        )

        self.assertIn('config_map_aws_auth', terraform_template['locals'])
        self.assertIn('aws_iam_role.worker.arn', terraform_template['locals']['config_map_aws_auth'])
        self.assertIn('aws_auth', terraform_template['resource']['kubernetes_config_map'])
        self.assertEqual(
            terraform_template['resource']['kubernetes_config_map']['aws_auth'],
            {
                'metadata': [{
                    'name': 'aws-auth',
                    'namespace': 'kube-system',
                }],
                'data': {
                    'mapRoles': '${local.config_map_aws_auth}',
                }
            }
        )

    @patch('buildercore.terraform.Terraform')
    def test_helm_provider(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-eks-helm--%s' % self.environment
        context = cfngen.build_context('project-with-eks-helm', stackname=stackname)
        terraform.init(stackname, context)
        providers = self._load_terraform_file(stackname, 'providers')
        self.assertIn('helm', providers['provider'].keys())
        self.assertEqual(
            {
                'version': "= %s" % '0.9.0',
                'kubernetes': {
                    'host': '${data.aws_eks_cluster.main.endpoint}',
                    'cluster_ca_certificate': '${base64decode(data.aws_eks_cluster.main.certificate_authority.0.data)}',
                    'token': '${data.aws_eks_cluster_auth.main.token}',
                    'load_config_file': False,
                },
                'service_account': '${kubernetes_cluster_role_binding.tiller.subject.0.name}',
            },
            providers['provider']['helm']
        )

    def test_eks_and_helm(self):
        pname = 'project-with-eks-helm'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertIn('tiller', terraform_template['resource']['kubernetes_service_account'])
        self.assertEqual(
            terraform_template['resource']['kubernetes_service_account']['tiller'],
            {
                'metadata': {
                    'name': 'tiller',
                    'namespace': 'kube-system',
                },
            }
        )

        self.assertIn('tiller', terraform_template['resource']['kubernetes_cluster_role_binding'])
        self.assertEqual(
            terraform_template['resource']['kubernetes_cluster_role_binding']['tiller'],
            {
                'metadata': {
                    'name': 'tiller',
                },
                'role_ref': {
                    'api_group': 'rbac.authorization.k8s.io',
                    'kind': 'ClusterRole',
                    'name': 'cluster-admin',
                },
                'subject': [
                    {
                        'kind': 'ServiceAccount',
                        'name': '${kubernetes_service_account.tiller.metadata.0.name}',
                        'namespace': 'kube-system',
                    },
                ],
            }
        )

        self.assertIn('incubator', terraform_template['data']['helm_repository'])
        self.assertEqual(
            terraform_template['data']['helm_repository']['incubator'],
            {
                'name': 'incubator',
                'url': 'https://kubernetes-charts-incubator.storage.googleapis.com',
            }
        )

        self.assertIn('common_resources', terraform_template['resource']['helm_release'])
        self.assertEqual(
            terraform_template['resource']['helm_release']['common_resources'],
            {
                'name': 'common-resources',
                'repository': "${data.helm_repository.incubator.metadata.0.name}",
                'chart': 'incubator/raw',
                'depends_on': ['kubernetes_cluster_role_binding.tiller'],
            }
        )

    def test_eks_and_external_dns(self):
        pname = 'project-with-eks-external-dns'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        # Helm is a dependency
        self.assertIn('common_resources', terraform_template['resource']['helm_release'])

        self.assertIn('kubernetes_external_dns', terraform_template['resource']['aws_iam_policy'])
        self.assertEqual(
            '%s--AmazonRoute53KubernetesExternalDNS' % context['stackname'],
            terraform_template['resource']['aws_iam_policy']['kubernetes_external_dns']['name']
        )
        self.assertEqual(
            '/',
            terraform_template['resource']['aws_iam_policy']['kubernetes_external_dns']['path']
        )
        self.assertEqual(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "route53:ChangeResourceRecordSets",
                        ],
                        "Resource": [
                            "arn:aws:route53:::hostedzone/*",
                        ],
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "route53:ListHostedZones",
                            "route53:ListResourceRecordSets",
                        ],
                        "Resource": [
                            "*",
                        ],
                    },
                ]
            },
            json.loads(terraform_template['resource']['aws_iam_policy']['kubernetes_external_dns']['policy'])
        )

        self.assertIn('worker_external_dns', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            {
                'policy_arn': '${aws_iam_policy.kubernetes_external_dns.arn}',
                'role': "${aws_iam_role.worker.name}",
            },
            terraform_template['resource']['aws_iam_role_policy_attachment']['worker_external_dns']
        )

        self.assertIn('external_dns', terraform_template['resource']['helm_release'])
        self.assertEqual(
            {
                'name': 'external-dns',
                'chart': 'stable/external-dns',
                'version': '2.6.1',
                'depends_on': ['helm_release.common_resources'],
                'set': [
                    {
                        'name': 'image.tag',
                        'value': '0.5.16',
                    },
                    {
                        'name': 'sources[0]',
                        'value': 'service',
                    },
                    {
                        'name': 'provider',
                        'value': 'aws',
                    },
                    {
                        'name': 'domainFilters[0]',
                        'value': 'elifesciences.net',
                    },
                    {
                        'name': 'policy',
                        'value': 'sync',
                    },
                    {
                        'name': 'aws.zoneType',
                        'value': 'public', # 'private',
                    },
                    {
                        'name': 'txtOwnerId',
                        'value': context['stackname'],
                    },
                    {
                        'name': 'rbac.create',
                        'value': 'true',
                    }
                ],
            },
            terraform_template['resource']['helm_release']['external_dns']
        )

    def test_eks_and_efs(self):
        pname = 'project-with-eks-efs'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertIn('kubernetes_efs', terraform_template['resource']['aws_iam_policy'])
        self.assertEqual(
            '%s--AmazonEFSKubernetes' % context['stackname'],
            terraform_template['resource']['aws_iam_policy']['kubernetes_efs']['name']
        )
        self.assertEqual(
            '/',
            terraform_template['resource']['aws_iam_policy']['kubernetes_efs']['path']
        )
        self.assertEqual(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "elasticfilesystem:*",
                        ],
                        "Resource": [
                            "*",
                        ],
                    },
                ]
            },
            json.loads(terraform_template['resource']['aws_iam_policy']['kubernetes_efs']['policy'])
        )

        self.assertIn('worker_efs', terraform_template['resource']['aws_iam_role_policy_attachment'])
        self.assertEqual(
            {
                'policy_arn': '${aws_iam_policy.kubernetes_efs.arn}',
                'role': "${aws_iam_role.worker.name}",
            },
            terraform_template['resource']['aws_iam_role_policy_attachment']['worker_efs']
        )

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
        filename = terraform.write_template('dummy1--%s' % self.environment, contents)
        self.assertEqual(filename, '.cfn/terraform/dummy1--%s/generated.tf.json' % self.environment)
        self.assertEqual(terraform.read_template('dummy1--%s' % self.environment), contents)

    def _parse_template(self, terraform_template):
        """use yaml module to load JSON to avoid large u'foo' vs 'foo' string diffs
        https://stackoverflow.com/a/16373377/91590"""
        return yaml.safe_load(terraform_template)

    def _load_terraform_file(self, stackname, filename):
        with open(join(terraform.TERRAFORM_DIR, stackname, '%s.tf.json' % filename), 'r') as fp:
            return self._parse_template(fp.read())
