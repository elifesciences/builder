from collections import namedtuple, OrderedDict
import os, re, shutil, json
from os.path import join
from python_terraform import Terraform, IsFlagged, IsNotFlagged
from .config import BUILDER_BUCKET, BUILDER_REGION, TERRAFORM_DIR, PROJECT_PATH
from .context_handler import only_if, load_context
from .utils import ensure, mkdir_p
from . import fastly

EMPTY_TEMPLATE = '{}'
PROVIDER_FASTLY_VERSION = '0.4.0',
PROVIDER_VAULT_VERSION = '1.3'

RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'

DATA_TYPE_VAULT_GENERIC_SECRET = 'vault_generic_secret'
DATA_TYPE_HTTP = 'http'
DATA_TYPE_TEMPLATE = 'template_file'
DATA_NAME_VAULT_GCS_LOGGING = 'fastly-gcs-logging'
DATA_NAME_VAULT_GCP_LOGGING = 'fastly-gcp-logging'
DATA_NAME_VAULT_FASTLY_API_KEY = 'fastly'
DATA_NAME_VAULT_GCP_API_KEY = 'gcp'
DATA_NAME_VAULT_GITHUB = 'github'

# keys to lookup in Vault
# cannot modify these without putting new values inside Vault:
#     VAULT_ADDR=https://...:8200 vault put secret/builder/apikey/fastly-gcs-logging email=... secret_key=@~/file.json
VAULT_PATH_FASTLY = 'secret/builder/apikey/fastly'
VAULT_PATH_FASTLY_GCS_LOGGING = 'secret/builder/apikey/fastly-gcs-logging'
VAULT_PATH_FASTLY_GCP_LOGGING = 'secret/builder/apikey/fastly-gcp-logging'
VAULT_PATH_GCP = 'secret/builder/apikey/gcp'
VAULT_PATH_GITHUB = 'secret/builder/apikey/github'

FASTLY_GZIP_TYPES = ['text/html', 'application/x-javascript', 'text/css', 'application/javascript',
                     'text/javascript', 'application/json', 'application/vnd.ms-fontobject',
                     'application/x-font-opentype', 'application/x-font-truetype',
                     'application/x-font-ttf', 'application/xml', 'font/eot', 'font/opentype',
                     'font/otf', 'image/svg+xml', 'image/vnd.microsoft.icon', 'text/plain',
                     'text/xml']
FASTLY_GZIP_EXTENSIONS = ['css', 'js', 'html', 'eot', 'ico', 'otf', 'ttf', 'json']
FASTLY_LOG_FORMAT = """{
  "timestamp":"%{begin:%Y-%m-%dT%H:%M:%S}t",
  "time_elapsed":%{time.elapsed.usec}V,
  "object_hits": %{obj.hits}V,
  "object_lastuse": "%{obj.lastuse}V",
  "is_tls":%{if(req.is_ssl, "true", "false")}V,
  "client_ip":"%{req.http.Fastly-Client-IP}V",
  "forwarded_for": "%{req.http.X-Forwarded-For}V",
  "geo_city":"%{client.geo.city}V",
  "geo_country_code":"%{client.geo.country_code}V",
  "pop_datacenter": "%{server.datacenter}V",
  "pop_region": "%{server.region}V",
  "request":"%{req.request}V",
  "original_host":"%{req.http.X-Forwarded-Host}V",
  "host":"%{req.http.Host}V",
  "url":"%{cstr_escape(req.url)}V",
  "request_referer":"%{cstr_escape(req.http.Referer)}V",
  "request_user_agent":"%{cstr_escape(req.http.User-Agent)}V",
  "request_accept":"%{cstr_escape(req.http.Accept)}V",
  "request_accept_language":"%{cstr_escape(req.http.Accept-Language)}V",
  "request_accept_charset":"%{cstr_escape(req.http.Accept-Charset)}V",
  "response_status": "%>s",
  "cache_status":"%{regsub(fastly_info.state, "^(HIT-(SYNTH)|(HITPASS|HIT|MISS|PASS|ERROR|PIPE)).*", "\\\\2\\\\3") }V"
}"""

# Fastly proprietary evolutions of the standard Apache log format
# https://docs.fastly.com/guides/streaming-logs/custom-log-formats#advantages-of-using-the-version-2-custom-log-format
# It's in the API:
# https://docs.fastly.com/api/logging#logging_gcs
# Not supported yet by Terraform however:
# https://www.terraform.io/docs/providers/fastly/r/service_v1.html#name-12
# FASTLY_LOG_FORMAT_VERSION = 2

# what to prefix lines with, syslog heritage
# see https://docs.fastly.com/guides/streaming-logs/changing-log-line-formats#available-message-formats
FASTLY_LOG_LINE_PREFIX = 'blank' # no prefix

# keeps different logging configurations unique in the syslog implementation
# used by Fastly, avoiding
#     fastly_service_v1.fastly-cdn: 409 - Conflict:
#     Title:  Duplicate record
#     Detail: Duplicate logging_syslog: 'default'
FASTLY_LOG_UNIQUE_IDENTIFIERS = {
    'gcs': 'default', # historically the first one
    'bigquery': 'bigquery',
}

# at the moment VCL snippets are unsupported, this can be worked
# around by using a full VCL
# https://github.com/terraform-providers/terraform-provider-fastly/issues/7 tracks when snippets could become available in Terraform
FASTLY_MAIN_VCL_KEY = 'main'

def render(context):
    template = TerraformTemplate()
    fn_list = [
        render_fastly,
        render_gcs,
        render_bigquery,
        render_eks,
    ]
    for fn in fn_list:
        fn(context, template)

    generated_template = template.to_dict()

    if not generated_template:
        return EMPTY_TEMPLATE

    return json.dumps(generated_template)

def render_fastly(context, template):
    if not context['fastly']:
        return {}

    backends = []
    conditions = []
    request_settings = []
    headers = []
    vcl_constant_snippets = context['fastly']['vcl']
    vcl_templated_snippets = OrderedDict()

    request_settings.append(_fastly_request_setting({
        'name': 'force-ssl',
        'force_ssl': True,
    }))

    all_allowed_subdomains = context['fastly']['subdomains'] + context['fastly']['subdomains-without-dns']

    if context['fastly']['backends']:
        for name, backend in context['fastly']['backends'].items():
            if backend.get('condition'):
                condition_name = 'backend-%s-condition' % name
                conditions.append({
                    'name': condition_name,
                    'statement': backend.get('condition'),
                    'type': 'REQUEST',
                })
                request_settings.append(_fastly_request_setting({
                    'name': 'backend-%s-request-settings' % name,
                    'request_condition': condition_name,
                }))
                backend_condition_name = condition_name
            else:
                backend_condition_name = None
            shield = backend['shield'].get('pop')
            backends.append(_fastly_backend(
                backend['hostname'],
                name=name,
                request_condition=backend_condition_name,
                shield=shield
            ))
    else:
        shield = context['fastly']['shield'].get('pop')
        backends.append(_fastly_backend(
            context['full_hostname'],
            name=context['stackname'],
            shield=shield
        ))

    template.populate_resource(
        RESOURCE_TYPE_FASTLY,
        RESOURCE_NAME_FASTLY,
        block={
            'name': context['stackname'],
            'domain': [
                {'name': subdomain} for subdomain in all_allowed_subdomains
            ],
            'backend': backends,
            'default_ttl': context['fastly']['default-ttl'],
            'gzip': {
                'name': 'default',
                # shouldn't need to replicate the defaults
                # https://github.com/terraform-providers/terraform-provider-fastly/issues/66
                'content_types': sorted(FASTLY_GZIP_TYPES),
                'extensions': sorted(FASTLY_GZIP_EXTENSIONS),
            },
            'force_destroy': True,
            'vcl': []
        }
    )

    if context['fastly']['healthcheck']:
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'healthcheck',
            block={
                'name': 'default',
                'host': context['full_hostname'],
                'path': context['fastly']['healthcheck']['path'],
                'check_interval': context['fastly']['healthcheck']['check-interval'],
                'timeout': context['fastly']['healthcheck']['timeout'],
            }
        )
        for b in template.resource[RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['backend']:
            b['healthcheck'] = 'default'

    _render_fastly_vcl_templates(context, template, vcl_templated_snippets)
    _render_fastly_errors(context, template, vcl_templated_snippets)

    if context['fastly']['gcslogging']:
        gcslogging = context['fastly']['gcslogging']
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'gcslogging',
            block={
                'name': FASTLY_LOG_UNIQUE_IDENTIFIERS['gcs'],
                'bucket_name': gcslogging['bucket'],
                # TODO: validate it starts with /
                'path': gcslogging['path'],
                'period': gcslogging.get('period', 3600),
                'format': FASTLY_LOG_FORMAT,
                # not supported yet
                #'format_version': FASTLY_LOG_FORMAT_VERSION,
                'message_type': FASTLY_LOG_LINE_PREFIX,
                'email': "${data.%s.%s.data[\"email\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCS_LOGGING),
                'secret_key': "${data.%s.%s.data[\"secret_key\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCS_LOGGING),
            }
        )
        template.populate_data(
            DATA_TYPE_VAULT_GENERIC_SECRET,
            DATA_NAME_VAULT_GCS_LOGGING,
            block={
                'path': VAULT_PATH_FASTLY_GCS_LOGGING,
            }
        )

    if context['fastly']['bigquerylogging']:
        bigquerylogging = context['fastly']['bigquerylogging']
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'bigquerylogging',
            block={
                'name': FASTLY_LOG_UNIQUE_IDENTIFIERS['bigquery'],
                'project_id': bigquerylogging['project'],
                'dataset': bigquerylogging['dataset'],
                'table': bigquerylogging['table'],
                'format': FASTLY_LOG_FORMAT,
                'email': "${data.%s.%s.data[\"email\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCP_LOGGING),
                'secret_key': "${data.%s.%s.data[\"secret_key\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCP_LOGGING),
            }
        )
        template.populate_data(
            DATA_TYPE_VAULT_GENERIC_SECRET,
            DATA_NAME_VAULT_GCP_LOGGING,
            {
                'path': VAULT_PATH_FASTLY_GCP_LOGGING,
            }
        )

    if vcl_constant_snippets or vcl_templated_snippets:
        # constant snippets
        [template.populate_resource_element(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'vcl',
            {
                'name': snippet_name,
                'content': _generate_vcl_file(context['stackname'], fastly.VCL_SNIPPETS[snippet_name].content, snippet_name),
            }) for snippet_name in vcl_constant_snippets]

        # templated snippets
        [template.populate_resource_element(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'vcl',
            {
                'name': snippet_name,
                'content': '${data.template_file.%s.rendered}' % snippet_name,
            }) for snippet_name in vcl_templated_snippets]

        # main
        linked_main_vcl = fastly.MAIN_VCL_TEMPLATE
        inclusions = [fastly.VCL_SNIPPETS[name].as_inclusion() for name in vcl_constant_snippets] + list(vcl_templated_snippets.values())
        inclusions.reverse()
        for i in inclusions:
            linked_main_vcl = i.insert_include(linked_main_vcl)

        template.populate_resource_element(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'vcl',
            block={
                'name': FASTLY_MAIN_VCL_KEY,
                'content': _generate_vcl_file(
                    context['stackname'],
                    linked_main_vcl,
                    FASTLY_MAIN_VCL_KEY
                ),
                'main': True,
            }
        )

    if context['fastly']['surrogate-keys']:
        for name, surrogate in context['fastly']['surrogate-keys'].items():
            for sample_name, sample in surrogate.get('samples', {}).items():
                # check sample['url'] parsed leads to sample['value']
                match = re.match(surrogate['url'], sample['path'])
                ensure(match is not None, "Regex %s does not match sample %s" % (surrogate['url'], sample))
                sample_actual = match.expand(surrogate['value'])
                ensure(sample_actual == sample['expected'], "Incorrect generated surrogate key `%s` for sample %s" % (sample_actual, sample))

            cache_condition = {
                'name': 'condition-surrogate-%s' % name,
                'statement': 'req.url ~ "%s"' % surrogate['url'],
                'type': 'CACHE',
            }
            conditions.append(cache_condition)
            headers.append({
                'name': 'surrogate-keys %s' % name,
                'destination': "http.surrogate-key",
                'source': 'regsub(req.url, "%s", "%s")' % (surrogate['url'], surrogate['value']),
                'type': 'cache',
                'action': 'set',
                'ignore_if_set': True,
                'cache_condition': cache_condition['name'],
            })

    if conditions:
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'condition',
            block=conditions
        )

    if headers:
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'header',
            block=headers
        )

    if request_settings:
        template.populate_resource(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'request_setting',
            block=request_settings
        )

    return template.to_dict()


def _render_fastly_vcl_templates(context, template, vcl_templated_snippets):
    for name, variables in context['fastly']['vcl-templates'].items():
        vcl_template = fastly.VCL_TEMPLATES[name]
        vcl_template_file = _generate_vcl_file(
            context['stackname'],
            vcl_template.content,
            vcl_template.name,
            extension='vcl.tpl'
        )

        template.populate_data(
            DATA_TYPE_TEMPLATE,
            name,
            {
                'template': vcl_template_file,
                'vars': variables,
            }
        )

        vcl_templated_snippets[name] = vcl_template.as_inclusion()


def _render_fastly_errors(context, template, vcl_templated_snippets):
    if context['fastly']['errors']:
        error_vcl_template = fastly.VCL_TEMPLATES['error-page']
        error_vcl_template_file = _generate_vcl_file(
            context['stackname'],
            error_vcl_template.content,
            error_vcl_template.name,
            extension='vcl.tpl'
        )
        errors = context['fastly']['errors']
        codes = errors.get('codes', {})
        fallbacks = errors.get('fallbacks', {})
        for code, path in codes.items():
            template.populate_data(
                DATA_TYPE_HTTP,
                'error-page-%d' % code,
                block={
                    'url': '%s%s' % (errors['url'], path),
                }
            )

            name = 'error-page-vcl-%d' % code
            template.populate_data(
                DATA_TYPE_TEMPLATE,
                name,
                {
                    'template': error_vcl_template_file,
                    'vars': {
                        'test': 'obj.status == %s' % code,
                        'synthetic_response': '${data.http.error-page-%s.body}' % code,
                    },
                }
            )
            vcl_templated_snippets[name] = error_vcl_template.as_inclusion(name)
        if fallbacks.get('4xx'):
            template.populate_data(
                DATA_TYPE_HTTP,
                'error-page-4xx',
                {
                    'url': '%s%s' % (errors['url'], fallbacks.get('4xx')),
                }
            )
            name = 'error-page-vcl-4xx'
            template.populate_data(
                DATA_TYPE_TEMPLATE,
                name,
                {
                    'template': error_vcl_template_file,
                    'vars': {
                        'test': 'obj.status >= 400 && obj.status <= 499',
                        'synthetic_response': '${data.http.error-page-4xx.body}',
                    },
                }
            )
            vcl_templated_snippets[name] = error_vcl_template.as_inclusion(name)
        if fallbacks.get('5xx'):
            template.populate_data(
                DATA_TYPE_HTTP,
                'error-page-5xx',
                {
                    'url': '%s%s' % (errors['url'], fallbacks.get('5xx')),
                }
            )
            name = 'error-page-vcl-5xx'
            template.populate_data(
                DATA_TYPE_TEMPLATE,
                name,
                {
                    'template': error_vcl_template_file,
                    'vars': {
                        'test': 'obj.status >= 500 && obj.status <= 599',
                        'synthetic_response': '${data.http.error-page-5xx.body}',
                    }
                }
            )
            vcl_templated_snippets[name] = error_vcl_template.as_inclusion(name)


def _fastly_backend(hostname, name, request_condition=None, shield=None):
    backend_resource = {
        'address': hostname,
        'name': name,
        'port': 443,
        'use_ssl': True,
        'ssl_cert_hostname': hostname,
        'ssl_sni_hostname': hostname,
        'ssl_check_cert': True,
    }
    if request_condition:
        backend_resource['request_condition'] = request_condition
    if shield:
        backend_resource['shield'] = shield
    return backend_resource

def _fastly_request_setting(override):
    request_setting_resource = {
        'name': 'default',
        # shouldn't need to replicate the defaults
        # https://github.com/terraform-providers/terraform-provider-fastly/issues/50
        # https://github.com/terraform-providers/terraform-provider-fastly/issues/67
        'timer_support': True,
        'xff': 'leave',
    }
    request_setting_resource.update(override)
    return request_setting_resource


def _generate_vcl_file(stackname, content, key, extension='vcl'):
    """
    creates a VCL on the filesystem, for Terraform to dynamically load it on apply

    content can be a string or any object that can be casted to a string
    """
    with _open(stackname, key, extension=extension, mode='w') as fp:
        fp.write(str(content))
        return '${file("%s")}' % os.path.basename(fp.name)

def render_gcs(context, template):
    if not context['gcs']:
        return {}

    for bucket_name, options in context['gcs'].items():
        template.populate_resource('google_storage_bucket', bucket_name, block={
            'name': bucket_name,
            'location': 'us-east4',
            'storage_class': 'REGIONAL',
            'project': options['project'],
        })

    return template.to_dict()

def render_bigquery(context, template):
    if not context['bigquery']:
        return {}

    tables = OrderedDict({})
    for dataset_id, dataset_options in context['bigquery'].items():
        for table_id, table_options in dataset_options['tables'].items():
            table_options['dataset_id'] = dataset_id
            table_options['project'] = dataset_options['project']
            tables[table_id] = table_options

    for dataset_id, options in context['bigquery'].items():
        template.populate_resource('google_bigquery_dataset', dataset_id, block={
            'dataset_id': dataset_id,
            'project': options['project'],
        })

    needs_github_token = False

    for table_id, table_options in tables.items():
        schema = table_options['schema']
        stackname = context['stackname']
        fqrn = "%s_%s" % (table_options['dataset_id'], table_id) # 'fully qualified resource name'

        if schema.startswith('https://'):
            # remote schema, add a 'http' provider and have terraform pull it down for us
            # https://www.terraform.io/docs/providers/http/data_source.html
            block = {'url': schema}
            schema_ref = '${data.http.%s.body}' % fqrn
            if schema.startswith('https://raw.githubusercontent.com/'):
                block['request_headers'] = {
                    'Authorization': 'token ${data.%s.%s.data["token"]}' % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GITHUB)
                }
                needs_github_token = True
            template.populate_data(
                DATA_TYPE_HTTP,
                fqrn,
                block=block
            )
        else:
            # local schema. the `schema` is relative to `PROJECT_PATH`
            schema_path = join(PROJECT_PATH, schema)
            schema_file = os.path.basename(schema)
            terraform_working_dir = join(TERRAFORM_DIR, stackname)
            mkdir_p(terraform_working_dir)
            shutil.copyfile(schema_path, join(terraform_working_dir, schema_file))
            schema_ref = '${file("%s")}' % schema_file

        template.populate_resource('google_bigquery_table', fqrn, block={
            # this refers to the dataset resource to express the implicit dependency
            # otherwise a table can be created before the dataset, which fails
            'dataset_id': "${google_bigquery_dataset.%s.dataset_id}" % dataset_id, # "dataset"
            'table_id': table_id, # "csv_report_380"
            'project': table_options['project'], # "elife-data-pipeline"
            'schema': schema_ref,
        })

    if needs_github_token:
        # TODO: extract and reuse as it's good for all data.http Github source,
        # not just for schemas
        template.populate_data(DATA_TYPE_VAULT_GENERIC_SECRET, 'github', block={
            'path': VAULT_PATH_GITHUB,
        })

    return template.to_dict()

def render_eks(context, template):
    if not context['eks']:
        return {}

    template.populate_resource('aws_eks_cluster', 'main', block={
        'name': 'project-with-eks--%s' % context['instance_id'],
        'role_arn': '${aws_iam_role.eks_master.arn}',
        'vpc_config': {
            'security_group_ids': ["${aws_security_group.kubernetes--%s.id}" % context['instance_id']],
            'subnet_ids': ["${var.subnet_id_1}", "${var.subnet_id_2}"],
        },
        'depends_on': [
            "aws_iam_role_policy_attachment.kubernetes--demo--AmazonEKSClusterPolicy",
            "aws_iam_role_policy_attachment.kubernetes--demo--AmazonEKSServicePolicy",
        ]
    })

    template.populate_resource('aws_iam_role', 'eks_master', block={
        'name': 'kubernetes--%s--AmazonEKSMasterRole' % context['instance_id'],
        'assume_role_policy': json.dumps({
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
        }),
    })

    return template.to_dict()

def write_template(stackname, contents):
    "optionally, store a terraform configuration file for the stack"
    # if the template isn't empty ...?
    if json.loads(contents):
        with _open(stackname, 'generated', mode='w') as fp:
            fp.write(contents)
            return fp.name

def read_template(stackname):
    with _open(stackname, 'generated', mode='r') as fp:
        return fp.read()

class TerraformTemplateError(RuntimeError):
    pass

class TerraformTemplate():
    def __init__(self, resource=None, data=None):
        if not resource:
            resource = OrderedDict()
        self.resource = resource
        if not data:
            data = OrderedDict()
        self.data = data

    # for naming see https://www.terraform.io/docs/configuration/resources.html#syntax
    def populate_resource(self, type, name, key=None, block=None):
        if not type in self.resource:
            self.resource[type] = OrderedDict()
        target = self.resource[type]
        if key:
            if not name in target:
                target[name] = OrderedDict()
            if key in target[name]:
                raise TerraformTemplateError(
                    "Resource %s being overwritten (%s)" % ((type, name, key), target[name][key])
                )
            target[name][key] = block
        else:
            target[name] = block

    # TODO: optional `key`?
    def populate_resource_element(self, type, name, key, block=None):
        if not type in self.resource:
            self.resource[type] = OrderedDict()
        target = self.resource[type]
        if not name in target:
            target[name] = OrderedDict()
        if not key in target[name]:
            target[name][key] = []
        target[name][key].append(block)

    def populate_data(self, type, name, block=None):
        if not type in self.data:
            self.data[type] = OrderedDict()
        if name in self.data[type]:
            raise TerraformTemplateError(
                "Data %s being overwritten (%s)" % ((type, name), self.data[type][name])
            )
        self.data[type][name] = block

    def to_dict(self):
        result = {}
        if self.resource:
            result['resource'] = self.resource
        if self.data:
            result['data'] = self.data
        return result


class TerraformDelta(namedtuple('TerraformDelta', ['plan_output'])):
    """represents a delta between and old and new Terraform generated template, showing which resources are being added, updated, or removed.

    Extends the namedtuple-generated class to add custom methods."""

    def __str__(self):
        return self.plan_output

def generate_delta(new_context):
    # simplification: unless Fastly is involved, the TerraformDelta will be empty
    # this should eventually be removed, for example after test_buildercore_cfngen tests have been ported to test_buildercore_cloudformation
    # TODO: what if the new context doesn't have fastly, but it was there before?
    if not new_context['fastly'] and not new_context['gcs'] and not new_context['bigquery']:
        return None

    new_template = render(new_context)
    write_template(new_context['stackname'], new_template)
    return plan(new_context)

@only_if('fastly', 'gcs', 'bigquery')
def bootstrap(stackname, context):
    plan(context)
    update(stackname, context)

def plan(context):
    terraform = init(context['stackname'], context)

    def _generate_plan():
        terraform.plan(input=False, no_color=IsFlagged, capture_output=False, raise_on_error=True, detailed_exitcode=IsNotFlagged, out='out.plan')
        return 'out.plan'

    def _explain_plan(plan_filename):
        return_code, stdout, stderr = terraform.plan(plan_filename, input=False, no_color=IsFlagged, raise_on_error=True, detailed_exitcode=IsNotFlagged)
        ensure(return_code == 0, "Exit code of `terraform plan out.plan` should be 0, not %s" % return_code)
        ensure(stderr == '', "Stderr of `terraform plan out.plan` should be empty:\n%s" % stderr)
        return _clean_stdout(stdout)

    return TerraformDelta(_explain_plan(_generate_plan()))

def _clean_stdout(stdout):
    stdout = re.sub(re.compile(r"The plan command .* as an argument.", re.MULTILINE | re.DOTALL), "", stdout)
    stdout = re.sub(re.compile(r"Note: .* is subsequently run.", re.MULTILINE | re.DOTALL), "", stdout)
    stdout = re.sub(re.compile(r"\n+", re.MULTILINE), "\n", stdout)
    return stdout

def init(stackname, context):
    working_dir = join(TERRAFORM_DIR, stackname) # ll: ./.cfn/terraform/project--prod/
    terraform = Terraform(working_dir=working_dir)
    with _open(stackname, 'backend', mode='w') as fp:
        fp.write(json.dumps({
            'terraform': {
                'backend': {
                    's3': {
                        'bucket': BUILDER_BUCKET,
                        'key': 'terraform/%s.tfstate' % stackname,
                        'region': BUILDER_REGION,
                    },
                },
            },
        }))
    with _open(stackname, 'providers', mode='w') as fp:
        # TODO: possibly remove unused providers
        # Terraform already prunes them when running, but would
        # simplify the .cfn/terraform/$stackname/ files
        fp.write(json.dumps({
            'provider': {
                'fastly': {
                    # exact version constraint
                    'version': "= %s" % PROVIDER_FASTLY_VERSION,
                    'api_key': "${data.%s.%s.data[\"api_key\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_FASTLY_API_KEY),
                },
                'aws': {
                    # TODO: pin version constraint
                    'region': context['aws']['region'],
                },
                'google': {
                    'version': "= %s" % '1.20.0',
                    'region': 'us-east4',
                    'credentials': "${data.%s.%s.data[\"credentials\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCP_API_KEY),
                },
                'vault': {
                    'address': context['vault']['address'],
                    # exact version constraint
                    'version': "= %s" % PROVIDER_VAULT_VERSION,
                },
            },
            'data': {
                DATA_TYPE_VAULT_GENERIC_SECRET: {
                    # TODO: this should not be used unless Fastly is involved
                    DATA_NAME_VAULT_FASTLY_API_KEY: {
                        'path': VAULT_PATH_FASTLY,
                    },
                    # TODO: this should not be used unless GCP is involved
                    DATA_NAME_VAULT_GCP_API_KEY: {
                        'path': VAULT_PATH_GCP,
                    },
                },
            },
        }))
    terraform.init(input=False, capture_output=False, raise_on_error=True)
    return terraform

def update_template(stackname):
    context = load_context(stackname)
    update(stackname, context)

@only_if('fastly', 'gcs', 'bigquery')
def update(stackname, context):
    terraform = init(stackname, context)
    terraform.apply('out.plan', input=False, capture_output=False, raise_on_error=True)

@only_if('fastly', 'gcs', 'bigquery')
def destroy(stackname, context):
    terraform = init(stackname, context)
    terraform.destroy(input=False, capture_output=False, raise_on_error=True)
    terraform_directory = join(TERRAFORM_DIR, stackname)
    shutil.rmtree(terraform_directory)

def _file_path_for_generation(stackname, name, extension='tf.json'):
    "builds a path for a file to be placed in conf.TERRAFORM_DIR"
    return join(TERRAFORM_DIR, stackname, '%s.%s' % (name, extension))

def _open(stackname, name, extension='tf.json', mode='r'):
    "`open`s a file in the conf.TERRAFORM_DIR belonging to given `stackname` (./.cfn/terraform/$stackname/)"
    terraform_directory = join(TERRAFORM_DIR, stackname)
    mkdir_p(terraform_directory)

    deprecated_path = join(TERRAFORM_DIR, stackname, '%s.tf' % name)
    if os.path.exists(deprecated_path):
        os.remove(deprecated_path)

    return open(_file_path_for_generation(stackname, name, extension), mode)
