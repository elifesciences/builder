from collections import namedtuple
import json
import os
from os.path import exists, join, basename
import re
import shutil
from python_terraform import Terraform, IsFlagged, IsNotFlagged
from .config import BUILDER_BUCKET, BUILDER_REGION, TERRAFORM_DIR
from .context_handler import only_if, load_context
from .utils import ensure, mkdir_p
from . import fastly

EMPTY_TEMPLATE = '{}'
PROVIDER_FASTLY_VERSION = '0.1.4',
PROVIDER_VAULT_VERSION = '1.1'

RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'

DATA_TYPE_VAULT_GENERIC_SECRET = 'vault_generic_secret'
DATA_TYPE_HTTP = 'http'
DATA_NAME_VAULT_GCS_LOGGING = 'fastly-gcs-logging'
DATA_NAME_VAULT_FASTLY_API_KEY = 'fastly'

# keys to lookup in Vault
# cannot modify these without putting new values inside Vault:
#     VAULT_ADDR=https://...:8200 vault put secret/builder/apikey/fastly-gcs-logging email=... secret_key=@~/file.json
VAULT_PATH_FASTLY = 'secret/builder/apikey/fastly'
VAULT_PATH_FASTLY_GCS_LOGGING = 'secret/builder/apikey/fastly-gcs-logging'

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
  "shield": "%{req.http.x-shield}V",
  "request":"%{req.request}V",
  "original_host":"%{req.http.Elife-Orig-Host}V",
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

# at the moment VCL snippets are unsupported, this can be worked
# around by using a full VCL
# https://github.com/terraform-providers/terraform-provider-fastly/issues/7 tracks when snippets could become available in Terraform
FASTLY_MAIN_VCL_KEY = 'main'

def render(context):
    generated_template = render_fastly(context)
    generated_template.update(render_gcp(context))

    if not generated_template:
        return EMPTY_TEMPLATE

    return json.dumps(generated_template)

def render_fastly(context):
    if not context['fastly']:
        return {}

    backends = []
    conditions = []
    request_settings = []
    headers = []
    data = {}

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
                    'default_host': backend['hostname'],
                    'request_condition': condition_name,
                }))
                backend_condition_name = condition_name
            else:
                request_settings.append(_fastly_request_setting({
                    'default_host': backend['hostname']
                }))
                backend_condition_name = None
            backends.append(_fastly_backend(
                backend['hostname'],
                name=name,
                request_condition=backend_condition_name
            ))
    else:
        request_settings.append(_fastly_request_setting({
            'default_host': context['full_hostname']
        }))
        backends.append(_fastly_backend(
            context['full_hostname'],
            name=context['stackname']
        ))

    all_allowed_subdomains = context['fastly']['subdomains'] + context['fastly']['subdomains-without-dns']
    tf_file = {
        'resource': {
            RESOURCE_TYPE_FASTLY: {
                # must be unique but only in a certain context like this, use some constants
                RESOURCE_NAME_FASTLY: {
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
                    'force_destroy': True
                }
            }
        },
    }

    if context['fastly']['healthcheck']:
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['healthcheck'] = {
            'name': 'default',
            'host': context['full_hostname'],
            'path': context['fastly']['healthcheck']['path'],
            'check_interval': context['fastly']['healthcheck']['check-interval'],
            'timeout': context['fastly']['healthcheck']['timeout'],
        }
        for b in tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['backend']:
            b['healthcheck'] = 'default'

    vcl_templated_snippets = {}
    if context['fastly']['errors']:

        error_vcl_template = _generate_vcl_file(
            context['stackname'],
            fastly.VCL_TEMPLATES['error-page'].content,
            fastly.VCL_TEMPLATES['error-page'].name,
            extension='vcl.tpl'
        )
        errors = context['fastly']['errors']
        data[DATA_TYPE_HTTP] = {}
        for code, path in errors['codes'].items():
            data[DATA_TYPE_HTTP]['error-page-%d' % code] = {
                'url': '%s%s' % (errors['url'], path),
            }
            name = 'error-page-vcl-%d' % code
            data['template_file'] = {
                name: {
                    'template': error_vcl_template,
                    'vars': {
                        'code': '%d' % code,
                        'synthetic_response': '${data.http.error-page-%s.body}' % code,
                    }
                },
            }
            vcl_templated_snippets[name] = fastly.VCL_TEMPLATES['error-page'].as_snippet(name)

    if context['fastly']['gcslogging']:
        gcslogging = context['fastly']['gcslogging']
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['gcslogging'] = {
            'name': 'default',
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
        data[DATA_TYPE_VAULT_GENERIC_SECRET] = {
            DATA_NAME_VAULT_GCS_LOGGING: {
                'path': VAULT_PATH_FASTLY_GCS_LOGGING,
            }
        }

    if context['fastly']['vcl']:
        # snippets
        vcl_snippets = context['fastly']['vcl']
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['vcl'] = [
            {
                'name': snippet_name,
                'content': _generate_vcl_file(context['stackname'], fastly.VCL_SNIPPETS[snippet_name].content, snippet_name),
            } for snippet_name in vcl_snippets
        ]

        # templates
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['vcl'].extend([
            {
                'name': snippet_name,
                'content': '${data.template_file.%s.rendered}' % name,
            } for snippet_name in vcl_templated_snippets
        ])

        # main

        linked_main_vcl = fastly.MAIN_VCL_TEMPLATE
        for name in vcl_snippets:
            snippet = fastly.VCL_SNIPPETS[name]
            linked_main_vcl = snippet.insert_include(linked_main_vcl)
        for name in vcl_templated_snippets:
            linked_main_vcl = vcl_templated_snippets[name].insert_include(linked_main_vcl)

        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['vcl'].append({
            'name': FASTLY_MAIN_VCL_KEY,
            'content': _generate_vcl_file(
                context['stackname'],
                linked_main_vcl,
                FASTLY_MAIN_VCL_KEY
            ),
            'main': True,
        })

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
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['condition'] = conditions

    if headers:
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['header'] = headers

    tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['request_setting'] = request_settings

    if data:
        tf_file['data'] = data

    return tf_file

def _fastly_backend(hostname, name, request_condition=None):
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
    return backend_resource

def _fastly_request_setting(override):
    request_setting_resource = {
        'name': 'default',
        'force_ssl': True,
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
        return '${file("%s")}' % basename(fp.name)

def render_gcp(context):
    if not context['gcs']:
        return {}

    return {
        'resource': {
            'google_storage_bucket': {
                bucket_name: {
                    'name': bucket_name,
                    'location': 'us-east4',
                    'storage_class': 'REGIONAL',
                    'project': options['project'],
                } for bucket_name, options in context['gcs'].items()
            },
        },
    }

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

class TerraformDelta(namedtuple('TerraformDelta', ['plan_output'])):
    """represents a delta between and old and new Terraform generated template, showing which resources are being added, updated, or removed.

    Extends the namedtuple-generated class to add custom methods."""

    def __str__(self):
        return self.plan_output

def generate_delta(new_context):
    # simplification: unless Fastly is involved, the TerraformDelta will be empty
    # this should eventually be removed, for example after test_buildercore_cfngen tests have been ported to test_buildercore_cloudformation
    # TODO: what if the new context doesn't have fastly, but it was there before?
    if not new_context['fastly'] and not new_context['gcs']:
        return None

    new_template = render(new_context)
    write_template(new_context['stackname'], new_template)
    return plan(new_context)

@only_if('fastly', 'gcs')
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
                'google': {
                    'version': "= %s" % '1.13.0',
                    'region': 'us-east4',
                },
                'vault': {
                    'address': context['vault']['address'],
                    # exact version constraint
                    'version': "= %s" % PROVIDER_VAULT_VERSION,
                },
            },
            'data': {
                DATA_TYPE_VAULT_GENERIC_SECRET: {
                    DATA_NAME_VAULT_FASTLY_API_KEY: {
                        'path': VAULT_PATH_FASTLY,
                    }
                }
            },
        }))
    terraform.init(input=False, capture_output=False, raise_on_error=True)
    return terraform

def update_template(stackname):
    context = load_context(stackname)
    update(stackname, context)

@only_if('fastly', 'gcs')
def update(stackname, context):
    terraform = init(stackname, context)
    terraform.apply('out.plan', input=False, capture_output=False, raise_on_error=True)

@only_if('fastly', 'gcs')
def destroy(stackname, context):
    terraform = init(stackname, context)
    terraform.destroy(input=False, capture_output=False, raise_on_error=True)
    terraform_directory = join(TERRAFORM_DIR, stackname)
    shutil.rmtree(terraform_directory)

def _file_path(stackname, name, extension='tf.json'):
    return join(TERRAFORM_DIR, stackname, '%s.%s' % (name, extension))

def _open(stackname, name, extension='tf.json', mode='r'):
    terraform_directory = join(TERRAFORM_DIR, stackname)
    mkdir_p(terraform_directory)
    # remove deprecated file
    deprecated_path = join(TERRAFORM_DIR, stackname, '%s.tf' % name)
    if exists(deprecated_path):
        os.remove(deprecated_path)
    return open(_file_path(stackname, name, extension), mode)
