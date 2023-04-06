from collections import namedtuple, OrderedDict
import os, re, shutil, json
from os.path import join
from python_terraform import Terraform, IsFlagged, IsNotFlagged
from .context_handler import only_if, load_context
from .utils import ensure, mkdir_p, lookup, updatein
from . import aws, fastly, config
import contextlib
import logging

LOG = logging.getLogger(__name__)

MANAGED_SERVICES = ['fastly', 'gcs', 'bigquery', 'eks']
only_if_managed_services_are_present = only_if(*MANAGED_SERVICES)

EMPTY_TEMPLATE = '{}'

RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'

DATA_TYPE_VAULT_GENERIC_SECRET = 'vault_generic_secret'
DATA_TYPE_HTTP = 'http'
DATA_TYPE_TEMPLATE = 'template_file'
DATA_TYPE_AWS_AMI = 'aws_ami'
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

IRSA_POLICY_TEMPLATES = {
    "kubernetes-autoscaler": lambda stackname, accountid: {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeAutoScalingInstances",
                    "autoscaling:DescribeLaunchConfigurations",
                    "autoscaling:DescribeTags",
                    "ec2:DescribeInstanceTypes",
                    "ec2:DescribeLaunchTemplateVersions"
                ],
                "Resource": ["*"]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "autoscaling:SetDesiredCapacity",
                    "autoscaling:TerminateInstanceInAutoScalingGroup"
                ],
                "Resource": [
                    "${aws_autoscaling_group.worker.arn}",
                ],
            },
        ],
    },
    "external-dns": lambda stackname, accountid: {
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
        ],
    },
    "aws-ebs-csi-driver": lambda stackname, accountid: {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateSnapshot",
                    "ec2:AttachVolume",
                    "ec2:DetachVolume",
                    "ec2:ModifyVolume",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeInstances",
                    "ec2:DescribeSnapshots",
                    "ec2:DescribeTags",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVolumesModifications"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateTags"
                ],
                "Resource": [
                    "arn:aws:ec2:*:*:volume/*",
                    "arn:aws:ec2:*:*:snapshot/*"
                ],
                "Condition": {
                    "StringEquals": {
                        "ec2:CreateAction": [
                            "CreateVolume",
                            "CreateSnapshot"
                        ]
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteTags"
                ],
                "Resource": [
                    "arn:aws:ec2:*:*:volume/*",
                    "arn:aws:ec2:*:*:snapshot/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateVolume"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "aws:RequestTag/ebs.csi.aws.com/cluster": "true"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateVolume"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "aws:RequestTag/CSIVolumeName": "*"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteVolume"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "ec2:ResourceTag/ebs.csi.aws.com/cluster": "true"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteVolume"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "ec2:ResourceTag/CSIVolumeName": "*"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteVolume"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "ec2:ResourceTag/kubernetes.io/created-for/pvc/name": "*"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteSnapshot"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "ec2:ResourceTag/CSIVolumeSnapshotName": "*"
                    }
                }
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DeleteSnapshot"
                ],
                "Resource": "*",
                "Condition": {
                    "StringLike": {
                        "ec2:ResourceTag/ebs.csi.aws.com/cluster": "true"
                    }
                }
            }
        ]
    },
}

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

# utils

@contextlib.contextmanager
def _open(stackname, name, extension='tf.json', mode='r'):
    """opens a file `name` in the `conf.TERRAFORM_DIR` belonging to given `stackname`.
    for example:
      ./.cfn/terraform/$stackname/$name.$extension
      ./.cfn/terraform/$stackname/$name
    """
    terraform_directory = join(config.TERRAFORM_DIR, stackname)
    mkdir_p(terraform_directory)

    # "./.cfn/terraform/journal--prod/generated.tf"
    # "./.cfn/terraform/journal--prod/backend.tf"
    # "./.cfn/terraform/journal--prod/providers.tf"
    # lsh@2023-04-04: '.tf' was deprecated in favour of '.tf.json'
    deprecated_path = join(config.TERRAFORM_DIR, stackname, '%s.tf' % name)
    if os.path.exists(deprecated_path):
        os.remove(deprecated_path)

    if extension:
        # "./.cfn/terraform/journal--prod/generated.tf.json"
        # "./.cfn/terraform/journal--prod/backend.tf.json"
        # "./.cfn/terraform/journal--prod/providers.tf.json"
        path = join(config.TERRAFORM_DIR, stackname, '%s.%s' % (name, extension))
    else:
        # "./.cfn/terraform/journal--prod/.terraform-version"
        path = join(config.TERRAFORM_DIR, stackname, '%s' % name)

    # lsh@2023-03-29: behaviour changed to resemble what you'd typically expect
    # when you `with open(...) as foo:`.
    # there haven't been any problems with files not being closed as far as I can tell.
    # return open(path, mode)
    with open(path, mode) as fh:
        yield fh

# fastly

def _generate_vcl_file(stackname, content, key, extension='vcl'):
    """
    creates a VCL on the filesystem, for Terraform to dynamically load it on apply

    content can be a string or any object that can be casted to a string
    """
    with _open(stackname, key, extension=extension, mode='w') as fp:
        fp.write(str(content))
        return '${file("%s")}' % os.path.basename(fp.name)

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

    # https://registry.terraform.io/providers/fastly/fastly/latest/docs/resources/service_v1#nested-schema-for-healthcheck
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
                # lsh@2021-06-14: while debugging 503 errors from end2end and continuumtest CDNs, Fastly support offered:
                # "I would suggest to change your healthcheck configuration
                # .initial value shouldn't be lower than threshold.
                # If .initial < .threshold, the backend will be initialized as Unhealthy state until
                # (.threshold - .initial) > number of healthchecks have happened and they all are pass."
                'initial': 2, # default is 2
                'threshold': 2, # default is 3
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
                # 'format_version': FASTLY_LOG_FORMAT_VERSION,
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

    if context['fastly']['ip-blacklist']:
        ip_blacklist_acl = {
            'name': 'ip_blacklist',
        }

        ip_blacklist_condition = {
            'name': 'ip-blacklist',
            'statement': 'client.ip ~ %s' % ip_blacklist_acl['name'],
            'type': 'REQUEST',
        }

        ip_blacklist_response_object = {
            'name': 'ip-blacklist',
            'status': 403,
            'response': 'Forbidden',
            'request_condition': ip_blacklist_condition['name']
        }

        template.populate_resource_element(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'acl',
            block=ip_blacklist_acl,
        )

        conditions.append(ip_blacklist_condition)

        template.populate_resource_element(
            RESOURCE_TYPE_FASTLY,
            RESOURCE_NAME_FASTLY,
            'response_object',
            block=ip_blacklist_response_object,
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

# GCS, Google Cloud Storage

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

# Google BigQuery

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
            schema_path = join(config.PROJECT_PATH, schema)
            schema_file = os.path.basename(schema)
            terraform_working_dir = join(config.TERRAFORM_DIR, stackname)
            mkdir_p(terraform_working_dir)
            shutil.copyfile(schema_path, join(terraform_working_dir, schema_file))
            schema_ref = '${file("%s")}' % schema_file

        table_block = {
            # this refers to the dataset resource to express the implicit dependency
            # otherwise a table can be created before the dataset, which fails
            'dataset_id': "${google_bigquery_dataset.%s.dataset_id}" % dataset_id, # "dataset"
            'table_id': table_id, # "csv_report_380"
            'project': table_options['project'], # "elife-data-pipeline"
            'schema': schema_ref,
        }
        if table_options.get('time-partitioning'):
            ensure(table_options['time-partitioning'].get('type') == 'DAY', "The only supported type of time partitioning for %s is `DAY`" % table_id)
            table_block['time_partitioning'] = table_options['time-partitioning']

        template.populate_resource('google_bigquery_table', fqrn, block=table_block)

    if needs_github_token:
        # TODO: extract and reuse as it's good for all data.http Github source,
        # not just for schemas
        template.populate_data(DATA_TYPE_VAULT_GENERIC_SECRET, 'github', block={
            'path': VAULT_PATH_GITHUB,
        })

    return template.to_dict()

# EKS

def _render_eks_iam_access(context, template):
    template.populate_data("tls_certificate", "oidc_cert", {
        'url': '${aws_eks_cluster.main.identity.0.oidc.0.issuer}'
    })

    template.populate_resource('aws_iam_openid_connect_provider', 'default', block={
        'client_id_list': ['sts.amazonaws.com'],
        'thumbprint_list': ['${data.tls_certificate.oidc_cert.certificates.0.sha1_fingerprint}'],
        'url': '${aws_eks_cluster.main.identity.0.oidc.0.issuer}'
    })

    if 'iam-roles' in context['eks'] and isinstance(context['eks']['iam-roles'], OrderedDict):
        for rolename, role_definition in context['eks']['iam-roles'].items():
            if 'policy-template' not in role_definition:
                raise RuntimeError("Please provide a valid policy-template from %s" % IRSA_POLICY_TEMPLATES.keys())

            if role_definition['policy-template'] not in IRSA_POLICY_TEMPLATES:
                raise RuntimeError("Could not find policy template with the name %s" % role_definition['policy-template'])

            if 'service-account' not in role_definition or 'namespace' not in role_definition:
                raise RuntimeError("Please provide both a service-account and namespace in the iam-roles definition")

            stackname = context['stackname']
            accountid = context['aws']['account-id']
            serviceaccount = role_definition['service-account']
            namespace = role_definition['namespace']

            policy = json.dumps(IRSA_POLICY_TEMPLATES[role_definition['policy-template']](stackname, accountid))

            assume_policy = json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Federated": "${aws_iam_openid_connect_provider.default.arn}",
                        },
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                "${aws_iam_openid_connect_provider.default.url}:sub": ["system:serviceaccount:%s:%s" % (namespace, serviceaccount)]
                            }
                        }
                    }
                ]
            })

            template.populate_resource('aws_iam_role', rolename, block={
                'name': '%s--%s' % (stackname, rolename),
                'assume_role_policy': assume_policy,
            })

            template.populate_resource('aws_iam_policy', rolename, block={
                'name': '%s--%s' % (stackname, rolename),
                'path': '/',
                'policy': policy,
            })

            template.populate_resource('aws_iam_role_policy_attachment', rolename, block={
                'policy_arn': "${aws_iam_policy.%s.arn}" % rolename,
                'role': "${aws_iam_role.%s.name}" % rolename,
            })

def _render_eks_user_access(context, template):
    template.populate_resource('aws_iam_role', 'user', block={
        'name': '%s--AmazonEKSUserRole' % context['stackname'],
        'assume_role_policy': json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": "arn:aws:iam::%s:root" % context['aws']['account-id'],
                    },
                    "Action": "sts:AssumeRole"
                },
            ],
        }),
    })

    template.populate_local('config_map_aws_auth', """
- rolearn: ${aws_iam_role.worker.arn}
  username: system:node:{{EC2PrivateDNSName}}
  groups:
    - system:bootstrappers
    - system:nodes
- rolearn: ${aws_iam_role.user.arn}
  groups:
    - system:masters
""")

    template.populate_resource('kubernetes_config_map', 'aws_auth', block={
        'metadata': [{
            'name': 'aws-auth',
            'namespace': 'kube-system',
        }],
        'data': {
            'mapRoles': '${local.config_map_aws_auth}',
        }
    })

def _render_eks_workers_autoscaling_group(context, template):
    template.populate_resource('aws_iam_instance_profile', 'worker', block={
        'name': '%s--worker' % context['stackname'],
        'role': '${aws_iam_role.worker.name}'
    })

    template.populate_data(DATA_TYPE_AWS_AMI, 'worker', block={
        'filter': {
            'name': 'name',
            'values': ['amazon-eks-node-%s-v*' % context['eks']['version']],
        },
        'most_recent': True,
        'owners': [aws.ACCOUNT_EKS_AMI],
    })

    # EKS currently documents this required userdata for EKS worker nodes to
    # properly configure Kubernetes applications on the EC2 instance.
    # We utilize a Terraform local here to simplify Base64 encoding this
    # information into the AutoScaling Launch Configuration.
    # More information: https://docs.aws.amazon.com/eks/latest/userguide/launch-workers.html
    template.populate_local('worker_userdata', """
#!/bin/bash
set -o xtrace
/etc/eks/bootstrap.sh --apiserver-endpoint '${aws_eks_cluster.main.endpoint}' --b64-cluster-ca '${aws_eks_cluster.main.certificate_authority.0.data}' '${aws_eks_cluster.main.name}'""")

    worker = {
        'associate_public_ip_address': True,
        'iam_instance_profile': '${aws_iam_instance_profile.worker.name}',
        'image_id': '${data.aws_ami.worker.id}',
        'instance_type': context['eks']['worker']['type'],
        'name_prefix': '%s--worker' % context['stackname'],
        'security_groups': ['${aws_security_group.worker.id}'],
        'user_data_base64': '${base64encode(local.worker_userdata)}',
        'lifecycle': {
            'create_before_destroy': True,
        },
    }
    root_volume_size = lookup(context, 'eks.worker.root.size', None)
    if root_volume_size:
        worker['root_block_device'] = {
            'volume_size': root_volume_size
        }
    template.populate_resource('aws_launch_configuration', 'worker', block=worker)

    autoscaling_group_tags = [
        {
            'key': k,
            'value': v,
            'propagate_at_launch': True,
        }
        for k, v in aws.generic_tags(context).items()
    ]
    autoscaling_group_tags.append({
        'key': 'kubernetes.io/cluster/%s' % context['stackname'],
        'value': 'owned',
        'propagate_at_launch': True,
    })
    template.populate_resource('aws_autoscaling_group', 'worker', block={
        'name': '%s--worker' % context['stackname'],
        'launch_configuration': '${aws_launch_configuration.worker.id}',
        'min_size': context['eks']['worker']['min-size'],
        'max_size': context['eks']['worker']['max-size'],
        'desired_capacity': context['eks']['worker']['desired-capacity'],
        'vpc_zone_identifier': [context['eks']['worker-subnet-id'], context['eks']['worker-redundant-subnet-id']],
        'tags': autoscaling_group_tags,
    })

def _render_eks_workers_role(context, template):
    template.populate_resource('aws_iam_role', 'worker', block={
        'name': '%s--AmazonEKSWorkerRole' % context['stackname'],
        'assume_role_policy': json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }),
    })

    template.populate_resource('aws_iam_role_policy_attachment', 'worker_connect', block={
        'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
        'role': "${aws_iam_role.worker.name}",
    })

    template.populate_resource('aws_iam_role_policy_attachment', 'worker_cni', block={
        'policy_arn': "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
        'role': "${aws_iam_role.worker.name}",
    })

    template.populate_resource('aws_iam_role_policy_attachment', 'worker_ecr', block={
        'policy_arn': "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
        'role': "${aws_iam_role.worker.name}",
    })

    if context['eks']['efs']:
        template.populate_resource('aws_iam_policy', 'kubernetes_efs', block={
            'name': '%s--AmazonEFSKubernetes' % context['stackname'],
            'path': '/',
            'description': 'Allows management of EFS resources',
            'policy': json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "elasticfilesystem:DescribeFileSystems",
                            "elasticfilesystem:DescribeMountTargets",
                            "elasticfilesystem:DescribeMountTargetSecurityGroups",
                            "elasticfilesystem:DescribeTags",
                        ],
                        "Resource": [
                            "*",
                        ],
                    },
                ],
            }),
        })

        template.populate_resource('aws_iam_role_policy_attachment', 'worker_efs', block={
            'policy_arn': "${aws_iam_policy.kubernetes_efs.arn}",
            'role': "${aws_iam_role.worker.name}",
        })

def _render_eks_workers_security_group(context, template):
    template.populate_resource('aws_security_group_rule', 'worker_to_master', block={
        'description': 'Allow pods to communicate with the cluster API Server',
        'from_port': 443,
        'protocol': 'tcp',
        'security_group_id': '${aws_security_group.master.id}',
        'source_security_group_id': '${aws_security_group.worker.id}',
        'to_port': 443,
        'type': 'ingress',
    })

    security_group_tags = aws.generic_tags(context)
    security_group_tags['kubernetes.io/cluster/%s' % context['stackname']] = 'owned'
    template.populate_resource('aws_security_group', 'worker', block={
        'name': '%s--worker' % context['stackname'],
        'description': 'Security group for all worker nodes in the cluster',
        'vpc_id': context['aws']['vpc-id'],
        'egress': {
            'from_port': 0,
            'to_port': 0,
            'protocol': '-1',
            'cidr_blocks': ['0.0.0.0/0'],
        },
        'tags': security_group_tags,
    })

    template.populate_resource('aws_security_group_rule', 'worker_to_worker', block={
        'description': 'Allow worker nodes to communicate with each other',
        'from_port': 0,
        'protocol': '-1',
        'security_group_id': '${aws_security_group.worker.id}',
        'source_security_group_id': '${aws_security_group.worker.id}',
        'to_port': 65535,
        'type': 'ingress',
    })

    template.populate_resource('aws_security_group_rule', 'master_to_worker', block={
        'description': 'Allow worker Kubelets and pods to receive communication from the cluster control plane',
        'from_port': 1025,
        'protocol': 'tcp',
        'security_group_id': '${aws_security_group.worker.id}',
        'source_security_group_id': '${aws_security_group.master.id}',
        'to_port': 65535,
        'type': 'ingress',
    })

    template.populate_resource('aws_security_group_rule', 'eks_public_to_worker', block={
        'description': "Allow worker to expose NodePort services",
        'from_port': 30000,
        'protocol': 'tcp',
        'security_group_id': '${aws_security_group.worker.id}',
        'to_port': 32767,
        'type': 'ingress',
        'cidr_blocks': ["0.0.0.0/0"],
    })

def _render_eks_master(context, template):
    template.populate_resource('aws_eks_cluster', 'main', block={
        'name': context['stackname'],
        'version': context['eks']['version'],
        'role_arn': '${aws_iam_role.master.arn}',
        'vpc_config': {
            'security_group_ids': ['${aws_security_group.master.id}'],
            'subnet_ids': [context['eks']['subnet-id'], context['eks']['redundant-subnet-id']],
        },
        'depends_on': [
            "aws_iam_role_policy_attachment.master_kubernetes",
            "aws_iam_role_policy_attachment.master_ecs",
        ]
    })

def _render_eks_master_role(context, template):
    template.populate_resource('aws_iam_role', 'master', block={
        'name': '%s--AmazonEKSMasterRole' % context['stackname'],
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

    template.populate_resource('aws_iam_role_policy_attachment', 'master_kubernetes', block={
        'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
        'role': "${aws_iam_role.master.name}",
    })

    template.populate_resource('aws_iam_role_policy_attachment', 'master_ecs', block={
        'policy_arn': "arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
        'role': "${aws_iam_role.master.name}",
    })

def _render_eks_master_security_group(context, template):
    security_group_tags = aws.generic_tags(context)
    security_group_tags['kubernetes.io/cluster/%s' % context['stackname']] = 'owned'
    template.populate_resource('aws_security_group', 'master', block={
        'name': '%s--master' % context['stackname'],
        'description': 'Cluster communication with worker nodes',
        'vpc_id': context['aws']['vpc-id'],
        'egress': {
            'from_port': 0,
            'to_port': 0,
            'protocol': '-1',
            'cidr_blocks': ['0.0.0.0/0'],
        },
        'tags': security_group_tags,
    })

def render_eks(context, template):
    "all from https://learn.hashicorp.com/terraform/aws/eks-intro"
    if not context['eks']:
        return {}

    _render_eks_master_security_group(context, template)
    _render_eks_master_role(context, template)
    _render_eks_master(context, template)
    _render_eks_workers_security_group(context, template)
    _render_eks_workers_role(context, template)
    _render_eks_workers_autoscaling_group(context, template)
    _render_eks_user_access(context, template)
    if lookup(context, 'eks.iam-oidc-provider', False):
        _render_eks_iam_access(context, template)

# ---

class TerraformTemplateError(RuntimeError):
    pass

class TerraformTemplate():
    def __init__(self, resource=None, data=None, locals_=None):
        if not resource:
            resource = OrderedDict()
        self.resource = resource
        if not data:
            data = OrderedDict()
        self.data = data
        if not locals_:
            locals_ = OrderedDict()
        self.locals_ = locals_

    # for naming see https://www.terraform.io/docs/configuration/resources.html#syntax
    def populate_resource(self, type, name, key=None, block=None):
        if type not in self.resource:
            self.resource[type] = OrderedDict()
        target = self.resource[type]
        if key:
            if name not in target:
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
        if type not in self.resource:
            self.resource[type] = OrderedDict()
        target = self.resource[type]
        if name not in target:
            target[name] = OrderedDict()
        if key not in target[name]:
            target[name][key] = []
        target[name][key].append(block)

    def populate_data(self, type, name, block=None):
        if type not in self.data:
            self.data[type] = OrderedDict()
        if name in self.data[type]:
            raise TerraformTemplateError(
                "Data %s being overwritten (%s)" % ((type, name), self.data[type][name])
            )
        self.data[type][name] = block

    def populate_local(self, name, value):
        self.locals_[name] = value

    def to_dict(self):
        result = {}
        if self.resource:
            result['resource'] = self.resource
        if self.data:
            result['data'] = self.data
        if self.locals_:
            result['locals'] = self.locals_
        return result

class TerraformDelta(namedtuple('TerraformDelta', ['plan_output'])):
    """represents a delta between and old and new Terraform generated template, showing which resources are being added, updated, or removed.

    Extends the namedtuple-generated class to add custom methods."""

    def __str__(self):
        return self.plan_output

# ---

def write_template(stackname, contents):
    "optionally, store a terraform configuration file for the stack"
    # if the template isn't empty ...?
    json_contents = json.loads(contents)
    if json_contents:
        with _open(stackname, 'generated', mode='w') as fp:
            fp.write(json.dumps(json_contents, indent=4))
            return fp.name

def read_template(stackname):
    with _open(stackname, 'generated', mode='r') as fp:
        return fp.read()

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

def generate_delta(new_context):
    # simplification: unless Fastly is involved, the TerraformDelta will be empty
    # this should eventually be removed, for example after test_buildercore_cfngen tests have been ported to test_buildercore_cloudformation
    # TODO: what if the new context doesn't have fastly, but it was there before?
    used_managed_services = [k for k in MANAGED_SERVICES if new_context[k]]
    if not used_managed_services:
        return None

    new_template = render(new_context)
    write_template(new_context['stackname'], new_template)
    return plan(new_context)

def plan(context):
    terraform = init(context['stackname'], context)

    def _generate_plan():
        terraform.plan(input=False, no_color=IsFlagged, capture_output=False, raise_on_error=True, detailed_exitcode=IsNotFlagged, out='out.plan')
        return 'out.plan'

    def _explain_plan(plan_filename):
        return_code, stdout, stderr = terraform.show(plan_filename, no_color=IsFlagged, raise_on_error=True, detailed_exitcode=IsNotFlagged)
        ensure(return_code == 0, "Exit code of `terraform show out.plan` should be 0, not %s" % return_code)
        # TODO: may not be empty if TF_LOG is used
        ensure(stderr == '', "Stderr of `terraform show out.plan` should be empty:\n%s" % stderr)
        return _clean_stdout(stdout)

    return TerraformDelta(_explain_plan(_generate_plan()))

def _clean_stdout(stdout):
    stdout = re.sub(re.compile(r"The plan command .* as an argument.", re.MULTILINE | re.DOTALL), "", stdout)
    stdout = re.sub(re.compile(r"Note: .* is subsequently run.", re.MULTILINE | re.DOTALL), "", stdout)
    stdout = re.sub(re.compile(r"\n+", re.MULTILINE), "\n", stdout)
    return stdout

def init(stackname, context):

    # Terraform prunes unused providers when running but conditionally adding them
    # here simplifies the `.cfn/terraform/$stackname/` files and any Terraform upgrades.

    providers = {'provider': [], 'data': {}}

    vault_projects = ['fastly', 'bigquery']
    need_vault = any(context.get(key) for key in vault_projects)
    if need_vault:
        providers['provider'].append(
            {
                'vault': {
                    'address': context['vault']['address'],
                    # exact version constraint
                    'version': "= %s" % context['terraform']['provider-vault']['version'],
                },
            },
        )

    if context.get('fastly'):
        providers['provider'].append({
            'fastly': {
                # exact version constraint
                'version': "= %s" % context['terraform']['provider-fastly']['version'],
                'api_key': "${data.%s.%s.data[\"api_key\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_FASTLY_API_KEY),
            },
        })
        path = f"data.{DATA_TYPE_VAULT_GENERIC_SECRET}.{DATA_NAME_VAULT_FASTLY_API_KEY}.path"
        # updates a deeply nested value. creates intermediate dictionaries when `create=True`.
        updatein(providers, path, VAULT_PATH_FASTLY, create=True)

    aws_projects = ['eks']
    need_aws = any(context.get(key) for key in aws_projects)
    if need_aws:
        providers['provider'].extend(
            [
                {
                    'aws': {
                        'version': "= %s" % context['terraform']['provider-aws']['version'],
                        'region': context['aws']['region'],
                    },
                },
            ]
        )

    gcp_projects = ['bigquery', 'gcs']
    need_gcp = any(context.get(key) for key in gcp_projects)
    if need_gcp:
        providers['provider'].extend(
            [
                {
                    'google': {
                        'version': "= %s" % context['terraform']['provider-google']['version'],
                        'region': 'us-east4',
                        'credentials': "${data.%s.%s.data[\"credentials\"]}" % (DATA_TYPE_VAULT_GENERIC_SECRET, DATA_NAME_VAULT_GCP_API_KEY),
                    },
                },
            ]
        )
        path = f"data.{DATA_TYPE_VAULT_GENERIC_SECRET}.{DATA_NAME_VAULT_GCP_API_KEY}.path"
        # updates a deeply nested value. creates intermediate dictionaries when `create=True`.
        updatein(providers, path, VAULT_PATH_GCP, create=True)

    if context.get('eks'):
        providers['provider'].append({'tls': {
            'version': "= %s" % context['terraform']['provider-tls']['version']
        }})
        providers['provider'].append({'kubernetes': {
            'version': "= %s" % context['terraform']['provider-eks']['version'],
            'host': '${data.aws_eks_cluster.main.endpoint}',
            'cluster_ca_certificate': '${base64decode(data.aws_eks_cluster.main.certificate_authority.0.data)}',
            'token': '${data.aws_eks_cluster_auth.main.token}',
            'load_config_file': False,
        }})
        providers['data']['aws_eks_cluster'] = {
            'main': {
                'name': '${aws_eks_cluster.main.name}',
            },
        }
        # https://github.com/elifesciences/issues/issues/5775#issuecomment-658111158
        providers['provider'].append({
            'aws': {
                'region': context['aws']['region'],
                'version': '= %s' % context['terraform']['provider-aws']['version'],
                'alias': 'eks_assume_role',
                'assume_role': {
                    'role_arn': '${aws_iam_role.user.arn}'
                }
            }
        })
        providers['data']['aws_eks_cluster_auth'] = {
            'main': {
                'provider': 'aws.eks_assume_role',
                'name': '${aws_eks_cluster.main.name}',
            },
        }

    backend = {
        'terraform': {
            # 'required_providers': {
            #    'fastly': {
            #        'source': 'fastly/fastly',
            #    }
            # },
            'backend': {
                's3': {
                    'bucket': config.BUILDER_BUCKET,
                    'key': 'terraform/%s.tfstate' % stackname,
                    'region': config.BUILDER_REGION,
                },
            },
        },
    }

    # 0.11.x => 0.13 transformations
    if context['terraform']['version'] == '0.13.7':
        # 'providers' now relies on a 'required_providers' block under 'terraform'
        # - https://developer.hashicorp.com/terraform/language/v1.1.x/providers/requirements
        def provider_to_required_provider(provider_dict):
            provider_name = list(provider_dict.keys())[0] # {'fastly': {'version': ..., ...}, ...} => 'fastly'
            # I regret not going with terraform.providers.foo now :(
            provider_context_key = "provider-" + provider_name # "provider-aws"
            default_source = 'hashicorp/' + provider_name # "hashicorp/aws"
            source = context['terraform'][provider_context_key].get('source', default_source)
            return (provider_name, {'source': source,
                                    # TODO: can we/should we exclude 'version' from 'providers' now?
                                    'version': provider_dict[provider_name]['version']})
        required_providers = dict(map(provider_to_required_provider, providers['provider']))
        backend['terraform']['required_providers'] = required_providers

    # ---

    # ensure tfenv knows which version of Terraform to use:
    # - https://github.com/tfutils/tfenv#terraform-version-file
    with _open(stackname, '.terraform-version', extension=None, mode='w') as fp:
        fp.write(context['terraform']['version'])

    terraform = Terraform(**{
        'working_dir': join(config.TERRAFORM_DIR, stackname), # "./.cfn/terraform/project--env/"
        'terraform_bin_path': config.TERRAFORM_BIN_PATH})

    try:
        rc, stdout, _ = terraform.cmd("version")
        ensure(rc == 0, "failed to query terraform for it's version.")
        LOG.info("\n-----------\n" + stdout + "---------")
    except ValueError:
        # "ValueError: not enough values to unpack (expected 3, got 0)"
        # we're probably testing and the Terraform object has been mocked.
        pass

    with _open(stackname, 'backend', mode='w') as fp:
        fp.write(json.dumps(backend, indent=4))

    with _open(stackname, 'providers', mode='w') as fp:
        fp.write(json.dumps(providers, indent=4))

    terraform.init(input=False, capture_output=False, raise_on_error=True)
    return terraform

@only_if_managed_services_are_present
def update(stackname, context):
    terraform = init(stackname, context)
    # lsh@2023-04-06: `var=None` to fix known bug in `python-terraform` with versions of terraform >0.11
    # - https://github.com/beelit94/python-terraform/issues/67
    terraform.apply('out.plan', input=False, capture_output=False, raise_on_error=True, var=None)

def update_template(stackname):
    context = load_context(stackname)
    update(stackname, context)

@only_if_managed_services_are_present
def destroy(stackname, context):
    terraform = init(stackname, context)
    terraform.destroy(input=False, capture_output=False, raise_on_error=True)
    terraform_directory = join(config.TERRAFORM_DIR, stackname)
    shutil.rmtree(terraform_directory)

@only_if_managed_services_are_present
def bootstrap(stackname, context):
    plan(context)
    update(stackname, context)
