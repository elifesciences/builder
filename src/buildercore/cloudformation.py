from collections import namedtuple
import logging
import backoff
import botocore
from . import core, trop
from .utils import ensure

LOG = logging.getLogger(__name__)

def render_template(context):
    pname = context['project_name']
    msg = 'could not render a CloudFormation template for %r' % pname
    ensure('aws' in context['project'], msg, ValueError)
    return trop.render(context)

def _log_backoff(event):
    LOG.warn("Backing off in validating project %s", event['args'][0])

@backoff.on_exception(backoff.expo, botocore.exceptions.ClientError, on_backoff=_log_backoff, max_time=30)
def validate_template(pname, rendered_template):
    "remote cloudformation template checks."
    conn = core.boto_conn(pname, 'cloudformation', client=True)
    return conn.validate_template(TemplateBody=rendered_template)

class CloudFormationDelta(namedtuple('Delta', ['plus', 'edit', 'minus'])):
    """represents a delta between and old and new CloudFormation generated template, showing which resources are being added, updated, or removed

    Extends the namedtuple-generated class to add custom methods."""
    @property
    def non_empty(self):
        return any([
            self.plus['Resources'],
            self.plus['Outputs'],
            self.edit['Resources'],
            self.edit['Outputs'],
            self.minus['Resources'],
            self.minus['Outputs'],
        ])

def bootstrap(stackname, context, parameters):
    stack_body = core.stack_json(stackname)
    conn = core.boto_conn(stackname, 'cloudformation')
    # http://boto3.readthedocs.io/en/latest/reference/services/cloudformation.html#CloudFormation.ServiceResource.create_stack
    conn.create_stack(StackName=stackname, TemplateBody=stack_body, Parameters=parameters)
