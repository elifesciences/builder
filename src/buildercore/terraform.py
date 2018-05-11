from collections import namedtuple
import json
import os
from os.path import exists, join, basename
import re
import shutil
from python_terraform import Terraform
from .config import BUILDER_BUCKET, BUILDER_REGION, TERRAFORM_DIR, ConfigurationError
from .context_handler import only_if
from .utils import ensure, mkdir_p

EMPTY_TEMPLATE = '{}'
PROVIDER_FASTLY_VERSION = '0.1.4',
RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'
RESOURCE_TYPE_VAULT = 'vault_generic_secret'
RESOURCE_NAME_VAULT_GCS_LOGGING = 'fastly-gcs-logging'

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
  "geo_city":"%{client.geo.city}V",
  "geo_country_code":"%{client.geo.country_code}V",
  "pop_datacenter": "%{server.datacenter}V",
  "pop_region": "%{server.region}V",
  "shield": "%{req.http.x-shield}V",
  "request":"%{req.request}V",
  "host":"%{req.http.Fastly-Orig-Host}V",
  "url":"%{cstr_escape(req.url)}V",
  "request_referer":"%{cstr_escape(req.http.Referer)}V",
  "request_user_agent":"%{cstr_escape(req.http.User-Agent)}V",
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
# taken from https://docs.fastly.com/guides/vcl/mixing-and-matching-fastly-vcl-with-custom-vcl#fastlys-vcl-boilerplate
# expands #FASTLY macros into generated VCL
FASTLY_MAIN_VCL_TEMPLATE = """
    sub vcl_recv {
      #FASTLY recv

      if (req.request != "HEAD" && req.request != "GET" && req.request != "FASTLYPURGE") {
        return(pass);
      }

      return(lookup);
    }

    sub vcl_fetch {
      #FASTLY fetch

      if ((beresp.status == 500 || beresp.status == 503) && req.restarts < 1 && (req.request == "GET" || req.request == "HEAD")) {
        restart;
      }

      if (req.restarts > 0) {
        set beresp.http.Fastly-Restarts = req.restarts;
      }

      if (beresp.http.Set-Cookie) {
        set req.http.Fastly-Cachetype = "SETCOOKIE";
        return(pass);
      }

      if (beresp.http.Cache-Control ~ "private") {
        set req.http.Fastly-Cachetype = "PRIVATE";
        return(pass);
      }

      if (beresp.status == 500 || beresp.status == 503) {
        set req.http.Fastly-Cachetype = "ERROR";
        set beresp.ttl = 1s;
        set beresp.grace = 5s;
        return(deliver);
      }

      if (beresp.http.Expires || beresp.http.Surrogate-Control ~ "max-age" || beresp.http.Cache-Control ~ "(s-maxage|max-age)") {
        # keep the ttl here
      } else {
        # apply the default ttl
        set beresp.ttl = 3600s;
      }

      return(deliver);
    }

    sub vcl_hit {
      #FASTLY hit

      if (!obj.cacheable) {
        return(pass);
      }
      return(deliver);
    }

    sub vcl_miss {
      #FASTLY miss
      return(fetch);
    }

    sub vcl_deliver {
      #FASTLY deliver
      return(deliver);
    }

    sub vcl_error {
      #FASTLY error
    }

    sub vcl_pass {
      #FASTLY pass
    }

    sub vcl_log {
      #FASTLY log
    }"""

"""VCL snippets that can be used to augment the default VCL

Due to Terraform limitations we are unable to pass these directly to the Fastly API, and have to build a whole VCL ourselves.

Terminology for fields comes from https://docs.fastly.com/api/config#snippet"""
class FastlyCustomVCLSnippet(namedtuple('FastlyCustomVCLSnippet', ['name', 'content', 'type'])):
    def insert_include(self, main_vcl):
        lines = main_vcl.splitlines()
        section_start = None
        for i, line in enumerate(lines):
            m = re.match(r"(?P<indentation> +)sub", line)
            if m:
                section_start = i
                break
        if section_start is None:
            raise RuntimeError()
        lines.insert(section_start + 1, '')
        lines.insert(
            section_start + 1, 
            '%s  include "%s"' % (m.group(1), self.name)
        )
        return "\n".join(lines)

FASTLY_CUSTOM_VCL = {
    'gzip-by-regex': FastlyCustomVCLSnippet(
        name='gzip-by-regex',
        content="""
        if ((beresp.status == 200 || beresp.status == 404) && (beresp.http.content-type ~ "(\+json)\s*($|;)" || req.url ~ "\.(css|js|html|eot|ico|otf|ttf|json|svg)($|\?)" ) ) {
          # always set vary to make sure uncompressed versions dont always win
          if (!beresp.http.Vary ~ "Accept-Encoding") {
            if (beresp.http.Vary) {
              set beresp.http.Vary = beresp.http.Vary ", Accept-Encoding";
            } else {
              set beresp.http.Vary = "Accept-Encoding";
            }
          }
          if (req.http.Accept-Encoding == "gzip") {
            set beresp.gzip = true;
          }
        }
        """,
        type='fetch'
    ),
}

def render(context):
    if not context['fastly']:
        return EMPTY_TEMPLATE

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
                    'backend': {
                        'address': context['full_hostname'],
                        'name': context['stackname'],
                        'port': 443,
                        'use_ssl': True,
                        'ssl_cert_hostname': context['full_hostname'],
                        'ssl_check_cert': True,
                    },
                    'request_setting': {
                        'name': 'default',
                        'force_ssl': True,
                        # shouldn't need to replicate the defaults
                        # https://github.com/terraform-providers/terraform-provider-fastly/issues/50
                        # https://github.com/terraform-providers/terraform-provider-fastly/issues/67
                        'timer_support': True,
                        'xff': 'leave',
                    },
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
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['backend']['healthcheck'] = 'default'

    if context['fastly']['gcslogging']:
        gcslogging = context['fastly']['gcslogging']
        # TODO: require FASTLY_GCS_EMAIL env variable
        # TODO: require FASTLY_GCS_SECRET env variable
        # how to define an env variable with new lines:
        # https://stackoverflow.com/a/36439943/91590
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
            'email': "${data.%s.%s.data[\"email\"]}" % (RESOURCE_TYPE_VAULT, RESOURCE_NAME_VAULT_GCS_LOGGING),
            'secret_key': "${data.%s.%s.data[\"secret_key\"]}" % (RESOURCE_TYPE_VAULT, RESOURCE_NAME_VAULT_GCS_LOGGING),
        }
        tf_file['data'] = {
            RESOURCE_TYPE_VAULT: {
                RESOURCE_NAME_VAULT_GCS_LOGGING: {
                    'path': 'secret/builder/apikey/fastly-gcs-logging',
                }
            }
        }

    if context['fastly']['vcl']:
        vcl = context['fastly']['vcl']
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['vcl'] = [
            {
                'name': template,
                'content': _generate_vcl_file(context['stackname'], FASTLY_CUSTOM_VCL[template].content, template),
            } for template in vcl
        ]
        tf_file['resource'][RESOURCE_TYPE_FASTLY][RESOURCE_NAME_FASTLY]['vcl'].append({
            'name': FASTLY_MAIN_VCL_KEY,
            'content': _generate_vcl_file(
                context['stackname'],
                FASTLY_MAIN_VCL_TEMPLATE, 
                FASTLY_MAIN_VCL_KEY
            ),
            'main': True,
        })

    return json.dumps(tf_file)

def _generate_vcl_file(stackname, content, key):
    with _open(stackname, key, extension='vcl', mode='w') as fp:
        fp.write(content)
        return '${file("%s")}' % basename(fp.name)

def _add_vcl_inclusion(vcl, names_to_sections):
    pass

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
        fp.write(json.dumps({
            'provider': {
                'fastly': {
                    # exact version constraint
                    'version': "= %s" % PROVIDER_FASTLY_VERSION,
                },
                'vault': {
                    'address': context['vault']['address'],
                },
            },
        }))
    terraform.init(input=False, capture_output=False, raise_on_error=True)
    return terraform

@only_if('fastly')
def update(stackname, context):
    ensure('FASTLY_API_KEY' in os.environ, "a FASTLY_API_KEY environment variable is required to provision Fastly resources. See https://manage.fastly.com/account/personal/tokens", ConfigurationError)
    terraform = init(stackname, context)
    terraform.apply(input=False, capture_output=False, raise_on_error=True)

@only_if('fastly')
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
