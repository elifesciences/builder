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
            'stackname': 'project-with-fastly-complex--prod',
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
                                    'address': 'prod-special.example.org',
                                    'name': 'articles',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'prod-special.example.org',
                                    'ssl_sni_hostname': 'prod-special.example.org',
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles-condition',
                                    'healthcheck': 'default',
                                    'shield': 'amsterdam-nl',
                                },
                                {
                                    'address': 'prod-special2.example.org',
                                    'name': 'articles2',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'prod-special2.example.org',
                                    'ssl_sni_hostname': 'prod-special2.example.org',
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles2-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
                                },
                                {
                                    'address': 'prod-special3.example.org',
                                    'name': 'articles3',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'prod-special3.example.org',
                                    'ssl_sni_hostname': 'prod-special3.example.org',
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles3-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
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
                                    'name': 'condition-surrogate-article-id',
                                    'statement': 'req.url ~ "^/articles/(\\d+)/(.+)$"',
                                    'type': 'CACHE',
                                },
                            ],
                            'vcl': [
                                {
                                    'name': 'gzip-by-content-type-suffix',
                                    'content': '${file("gzip-by-content-type-suffix.vcl")}',
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
            'stackname': 'project-with-fastly-shield--prod',
        }
        context = cfngen.build_context('project-with-fastly-shield', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'dca-dc-us')
        self.assertIn('domain', service)

    def test_fastly_template_shield_pop(self):
        extra = {
            'stackname': 'project-with-fastly-shield-pop--prod',
        }
        context = cfngen.build_context('project-with-fastly-shield-pop', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'london-uk')
        self.assertIn('domain', service)

    def test_fastly_template_shield_aws_region(self):
        base.switch_in_test_settings('dummy-settings2.yaml')
        extra = {
            'stackname': 'project-with-fastly-shield-aws-region--prod',
        }
        context = cfngen.build_context('project-with-fastly-shield-aws-region', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'frankfurt-de')

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
        bucket = template['resource']['google_storage_bucket']['widgets-prod']
        self.assertEqual(bucket, {
            'name': 'widgets-prod',
            'location': 'us-east4',
            'storage_class': 'REGIONAL',
            'project': 'elife-something',
        })

    def test_bigquery_datasets_only(self):
        extra = {
            'stackname': 'project-with-bigquery-datasets-only--prod',
        }
        context = cfngen.build_context('project-with-bigquery-datasets-only', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_prod']
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_prod',
            'project': 'elife-something',
        })

        self.assertNotIn('google_bigquery_table', template['resource'])

    def test_bigquery_full_template(self):
        extra = {
            'stackname': 'project-with-bigquery--prod',
        }
        context = cfngen.build_context('project-with-bigquery', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_prod']
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_prod',
            'project': 'elife-something',
        })

        table = template['resource']['google_bigquery_table']['my_dataset_prod_widgets']
        self.assertEqual(table, {
            'dataset_id': 'my_dataset_prod',
            'table_id': 'widgets',
            'project': 'elife-something',
            'schema': '${file("key-value.json")}',
        })

    def test_bigquery_remote_paths(self):
        "remote paths require terraform to fetch and load the files, which requires another entry in the 'data' list"
        pname = "project-with-bigquery-remote-schemas"
        iid = pname + "--prod"
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        expecting = json.loads('''{
            "resource": {
                "google_bigquery_dataset": {
                    "my_dataset_prod": {
                        "project": "elife-something",
                        "dataset_id": "my_dataset_prod"
                    }
                },
                "google_bigquery_table": {
                    "my_dataset_prod_remote": {
                        "project": "elife-something",
                        "dataset_id": "my_dataset_prod",
                        "table_id": "remote",
                        "schema": "${data.http.my_dataset_prod_remote.body}"
                    },
                    "my_dataset_prod_local": {
                        "project": "elife-something",
                        "dataset_id": "my_dataset_prod",
                        "table_id": "local",
                        "schema": "${file(\\"key-value.json\\")}"
                    }
                }
            },
            "data": {
                "http": {
                    "my_dataset_prod_remote": {
                        "url": "https://example.org/schemas/remote.json"
                    }
                }
            }
        }''')
        self.assertEqual(expecting, terraform_template)

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
