import json
from buildercore.utils import ensure

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
