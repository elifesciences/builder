from collections import namedtuple
import logging
import json
import backoff
import botocore
from . import core, trop
from .utils import call_while, ensure

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

EMPTY_STACK = {'Resources': {}}

def bootstrap(stackname, context, parameters):
    stack_body = core.stack_json(stackname)
    if json.loads(stack_body) == EMPTY_STACK:
        return

    conn = core.boto_conn(stackname, 'cloudformation')
    # http://boto3.readthedocs.io/en/latest/reference/services/cloudformation.html#CloudFormation.ServiceResource.create_stack
    conn.create_stack(StackName=stackname, TemplateBody=stack_body, Parameters=parameters)
    _wait_until_in_progress(stackname)

class StackTakingALongTimeToComplete(RuntimeError):
    pass

def _wait_until_in_progress(stackname):
    def is_updating(stackname):
        stack_status = core.describe_stack(stackname).stack_status
        LOG.info("Stack status: %s", stack_status)
        return stack_status in ['CREATE_IN_PROGRESS']
    call_while(
        partial(is_updating, stackname),
        timeout=7200,
        update_msg='Waiting for CloudFormation to finish creating stack ...',
        exception_class=StackTakingALongTimeToComplete
    )

    final_stack = core.describe_stack(stackname)
    # NOTE: stack.events.all|filter|limit can take 5+ seconds to complete regardless of events returned
    events = [(e.resource_status, e.resource_status_reason) for e in final_stack.events.all()]
    ensure(final_stack.stack_status in core.ACTIVE_CFN_STATUS,
           "Failed to create stack: %s.\nEvents: %s" % (final_stack.stack_status, pformat(events)))

def destroy(stackname, context):
    stack_body = core.stack_json(stackname)
    if json.loads(stack_body) == EMPTY_STACK:
        return

    core.describe_stack(stackname).delete()

    def is_deleting(stackname):
        try:
            return core.describe_stack(stackname).stack_status in ['DELETE_IN_PROGRESS']
        except botocore.exceptions.ClientError as err:
            if err.response['Error']['Message'].endswith('does not exist'):
                return False
            raise # not sure what happened, but we're not handling it here. die.
    call_while(partial(is_deleting, stackname), timeout=3600, update_msg='Waiting for CloudFormation to finish deleting stack ...')
