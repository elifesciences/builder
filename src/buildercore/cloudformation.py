import logging
import backoff
import boto
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

@backoff.on_exception(backoff.expo, boto.connection.BotoServerError, on_backoff=_log_backoff, max_time=30)
def validate_template(pname, rendered_template):
    "remote cloudformation template checks."
    conn = core.connect_aws_with_pname(pname, 'cfn')
    return conn.validate_template(rendered_template)
