import json
import os
from os.path import join
from python_terraform import Terraform
from buildercore.utils import ensure
from .config import BUILDER_BUCKET, BUILDER_REGION, TERRAFORM_DIR, ConfigurationError
from .context_handler import only_if

PROVIDER_FASTLY_VERSION = '0.1.4',
RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'

def render(context):
    if not context['fastly']:
        return '{}'

    tf_file = {
        'resource': {
            RESOURCE_TYPE_FASTLY: {
                # must be unique but only in a certain context like this, use some constants
                RESOURCE_NAME_FASTLY: {
                    'name': context['stackname'],
                    'domain': [
                        {'name': subdomain} for subdomain in context['fastly']['subdomains']
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
                    },
                    'force_destroy': True
                }
            }
        },
    }
    return json.dumps(tf_file)

def init(stackname):
    working_dir = join(TERRAFORM_DIR, stackname) # ll: ./.cfn/terraform/project--prod/
    terraform = Terraform(working_dir=working_dir)
    with open('%s/backend.tf' % working_dir, 'w') as fp:
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
    with open('%s/providers.tf' % working_dir, 'w') as fp:
        fp.write(json.dumps({
            'provider': {
                'fastly': {
                    # exact version constraint
                    'version': "= %s" % PROVIDER_FASTLY_VERSION,
                },
            },
        }))
    terraform.init(input=False, capture_output=False, raise_on_error=True)
    return terraform

@only_if('fastly')
def update(stackname, context):
    ensure('FASTLY_API_KEY' in os.environ, "a FASTLY_API_KEY environment variable is required to provision Fastly resources", ConfigurationError)
    terraform = init(stackname)
    terraform.apply(input=False, capture_output=False, raise_on_error=True)

@only_if('fastly')
def destroy(stackname, context):
    terraform = init(stackname)
    terraform.destroy(input=False, capture_output=False, raise_on_error=True)
    # TODO: also destroy files
