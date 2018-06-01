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

def read_template(stackname):
    "returns the contents of a cloudformation template as a python data structure"
    output_fname = os.path.join(config.STACK_DIR, stackname + ".json")
    return json.load(open(output_fname, 'r'))

def apply_delta(template, delta):
    for component in delta.plus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.plus[component])
        template[component] = data
    for component in delta.edit:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.edit[component])
        template[component] = data
    for component in delta.minus:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        for title in delta.minus[component]:
            del template[component][title]

def _merge_delta(stackname, delta):
    """Merges the new resources in delta in the local copy of the Cloudformation  template"""
    template = read_template(stackname)
    apply_delta(template, delta)
    # TODO: possibly pre-write the cloudformation template
    # the source of truth can always be redownloaded from the CloudFormation API
    write_template(stackname, json.dumps(template))
    return template

def write_template(stackname, contents):
    "writes a json version of the python cloudformation template to the stacks directory"
    output_fname = os.path.join(config.STACK_DIR, stackname + ".json")
    open(output_fname, 'w').write(contents)
    return output_fname

def update_template(stackname, delta):
    if delta.non_empty:
        new_template = _merge_delta(stackname, delta.cloudformation)
        _update_template(stackname, new_template)
    else:
        # attempting to apply an empty change set would result in an error
        LOG.info("Nothing to update on CloudFormation")

def _update_template(stackname, template):
    parameters = []
    pdata = project_data_for_stackname(stackname)
    if pdata['aws']['ec2']:
        parameters.append({'ParameterKey': 'KeyName', 'ParameterValue': stackname})
    try:
        conn = core.describe_stack(stackname)
        conn.update(TemplateBody=json.dumps(template), Parameters=parameters)
    except botocore.exceptions.ClientError as ex:
        # ex.response ll: {'ResponseMetadata': {'RetryAttempts': 0, 'HTTPStatusCode': 400, 'RequestId': 'dc28fd8f-4456-11e8-8851-d9346a742012', 'HTTPHeaders': {'x-amzn-requestid': 'dc28fd8f-4456-11e8-8851-d9346a742012', 'date': 'Fri, 20 Apr 2018 04:54:08 GMT', 'content-length': '288', 'content-type': 'text/xml', 'connection': 'close'}}, 'Error': {'Message': 'No updates are to be performed.', 'Code': 'ValidationError', 'Type': 'Sender'}}
        if ex.response['Error']['Message'] == 'No updates are to be performed.':
            LOG.info(str(ex), extra={'response': ex.response})
            return
        raise

    def stack_is_updating():
        return not core.stack_is(stackname, ['UPDATE_COMPLETE'], terminal_states=['UPDATE_ROLLBACK_COMPLETE'])

    waiting = "waiting for template of %s to be updated" % stackname
    done = "template of %s is in state UPDATE_COMPLETE" % stackname
    call_while(stack_is_updating, interval=2, timeout=7200, update_msg=waiting, done_msg=done)

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
