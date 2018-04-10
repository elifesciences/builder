import json
from os.path import join
from python_terraform import Terraform
from buildercore.utils import ensure
from .config import BUILDER_BUCKET, BUILDER_REGION, TERRAFORM_DIR

RESOURCE_TYPE_FASTLY = 'fastly_service_v1'
RESOURCE_NAME_FASTLY = 'fastly-cdn'

def render(context):
    if not context['fastly']:
        return '{}'

    ensure(len(context['fastly']['subdomains']) == 1, "Only 1 subdomain for Fastly CDNs is supported")

    tf_file = {
        'resource': {
            RESOURCE_TYPE_FASTLY: {
                # must be unique but only in a certain context like this, use some constants
                RESOURCE_NAME_FASTLY: {
                    'name': context['stackname'],
                    'domain': {
                        'name': context['fastly']['subdomains'][0],
                    },
                    'backend': {
                        'address': context['full_hostname'],
                        'name': context['stackname'],
                        'port': 443,
                        'use_ssl': True,
                        'ssl_check_cert': False # bad option
                        # it's for minimal fuss. Before we start customizing this, a lot of the risk to be tackled
                        # is integrating everything together with a good lifecycle for adding, modifying and removing
                        # CDNs that point to CloudFormation-managed resources.
                    },
                    'force_destroy': True
                }
            }
        },
    }
    return json.dumps(tf_file)

def init(stackname):
    working_dir = join(TERRAFORM_DIR, stackname) # ll: ./.cfn/terraform/project--prod/
    t = Terraform(working_dir=working_dir)
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
    t.init(input=False, capture_output=False, raise_on_error=True)
    return t

def destroy(stackname):
    pass
