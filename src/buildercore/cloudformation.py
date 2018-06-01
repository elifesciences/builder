from collections import namedtuple
from contextlib import contextmanager
import logging
import json
import os
from pprint import pformat
from functools import partial
import backoff
import botocore
from . import config, core, keypair, trop
from .utils import call_while, ensure

LOG = logging.getLogger(__name__)

def render_template(context):
    pname = context['project_name']
    msg = 'could not render a CloudFormation template for %r' % pname
    ensure('aws' in context['project'], msg, ValueError)
    return trop.render(context)

def _give_up_backoff(e):
    return e.response['Error']['Code'] != 'Throttling'

def _log_backoff(event):
    LOG.warn("Backing off in validating project %s", event['args'][0])

@backoff.on_exception(backoff.expo, botocore.exceptions.ClientError, on_backoff=_log_backoff, giveup=_give_up_backoff, max_time=30)
def validate_template(pname, rendered_template):
    "remote cloudformation template checks."
    if json.loads(rendered_template) == EMPTY_TEMPLATE:
        # empty templates are technically invalid, but they don't interact with CloudFormation at all
        return

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

EMPTY_TEMPLATE = {'Resources': {}}

def _noop():
    pass

@contextmanager
def stack_creation(stackname, on_start=_noop, on_error=_noop):
    try:
        on_start()
        yield

    except StackTakingALongTimeToComplete as err:
        LOG.info("Stack taking a long time to complete: %s", err)
        raise

    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'AlreadyExistsException':
            LOG.debug(err)
            return
        LOG.exception("unhandled boto ClientError attempting to create stack", extra={'stackname': stackname, 'response': err.response})
        on_error()
        raise

    except BaseException:
        LOG.exception("unhandled exception attempting to create stack", extra={'stackname': stackname})
        on_error()
        raise


def bootstrap(stackname, context):
    pdata = core.project_data_for_stackname(stackname)
    parameters = []
    on_start = _noop
    on_error = _noop
    if pdata['aws']['ec2']:
        parameters.append({'ParameterKey': 'KeyName', 'ParameterValue': stackname})
        on_start = lambda: keypair.create_keypair(stackname)
        on_error = lambda: keypair.delete_keypair(stackname)

    stack_body = core.stack_json(stackname)
    if json.loads(stack_body) == EMPTY_TEMPLATE:
        return

    if core.stack_is_active(stackname):
        LOG.info("stack exists") # avoid on_start handler
        return True

    with stack_creation(stackname, on_start=on_start, on_error=on_error):
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
    if json.loads(stack_body) == EMPTY_TEMPLATE:
        return

    try:
        core.describe_stack(stackname).delete()

        def is_deleting(stackname):
            try:
                return core.describe_stack(stackname).stack_status in ['DELETE_IN_PROGRESS']
            except botocore.exceptions.ClientError as err:
                if err.response['Error']['Message'].endswith('does not exist'):
                    return False
                raise # not sure what happened, but we're not handling it here. die.
        call_while(partial(is_deleting, stackname), timeout=3600, update_msg='Waiting for CloudFormation to finish deleting stack ...')
        _delete_stack_file(stackname)
        keypair.delete_keypair(stackname) # deletes the keypair wherever it can find it (locally, remotely)

    except botocore.exceptions.ClientError as ex:
        msg = "[%s: %s] %s (request-id: %s)"
        meta = ex.response['ResponseMetadata']
        err = ex.response['Error']
        # ll: [400: ValidationError] No updates are to be performed (request-id: dc28fd8f-4456-11e8-8851-d9346a742012)
        LOG.exception(msg, meta['HTTPStatusCode'], err['Code'], err['Message'], meta['RequestId'], extra={'response': ex.response})

def _delete_stack_file(stackname):
    path = os.path.join(config.STACK_DIR, stackname + ".json")
    if os.path.exists(path):
        os.unlink(path)
