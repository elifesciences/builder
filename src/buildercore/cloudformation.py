"""module concerns itself with the creation, updating and deleting of Cloudformation template instances.

see `trop.py` for the *generation* of Cloudformation templates."""

from collections import namedtuple
from contextlib import contextmanager
import logging
import json
import os
from pprint import pformat
from functools import partial
import backoff
import botocore
from . import config, core, keypair, trop, utils
from .utils import call_while, ensure

LOG = logging.getLogger(__name__)

def render_template(context):
    "generates an instance of a Cloudformation template using the given `context`."
    msg = 'could not render a CloudFormation template for %r' % context['project_name']
    ensure('aws' in context, msg, ValueError)
    return trop.render(context)

# ---

def _give_up_backoff(e):
    return e.response['Error']['Code'] != 'Throttling'

def _log_backoff(event):
    LOG.warning("Backing off in validating project %s", event['args'][0])

@backoff.on_exception(backoff.expo, botocore.exceptions.ClientError, on_backoff=_log_backoff, giveup=_give_up_backoff, max_time=30)
def validate_template(rendered_template):
    "remote cloudformation template checks."
    if json.loads(rendered_template) == EMPTY_TEMPLATE:
        # empty templates are technically invalid, but they don't interact with CloudFormation at all
        return
    conn = core.boto_client('cloudformation', region='us-east-1')
    return conn.validate_template(TemplateBody=rendered_template)

# ---

class CloudFormationDelta(namedtuple('Delta', ['plus', 'edit', 'minus'])):
    """represents a delta between and old and new CloudFormation generated template, showing which resources are being added, updated, or removed

    Extends the namedtuple-generated class to add custom methods."""
    @property
    def non_empty(self):
        return any([
            self.plus['Resources'],
            self.plus['Outputs'],
            self.plus['Parameters'],
            self.edit['Resources'],
            self.edit['Outputs'],
            self.minus['Resources'],
            self.minus['Outputs'],
            self.minus['Parameters'],
        ])
_empty_cloudformation_dictionary = {'Resources': {}, 'Outputs': {}, 'Parameters': {}}
CloudFormationDelta.__new__.__defaults__ = (_empty_cloudformation_dictionary, _empty_cloudformation_dictionary, _empty_cloudformation_dictionary)

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


# todo: rename. nothing is being bootstrapped here.
def bootstrap(stackname, context):
    "called by `bootstrap.create_stack` to generate a cloudformation template."
    parameters = []
    on_start = _noop
    on_error = _noop

    if context['ec2']:
        parameters.append({'ParameterKey': 'KeyName', 'ParameterValue': stackname})
        on_start = lambda: keypair.create_keypair(stackname)
        on_error = lambda: keypair.delete_keypair(stackname)

    stack_body = open(core.stack_path(stackname), 'r').read()
    if json.loads(stack_body) == EMPTY_TEMPLATE:
        LOG.warning("empty template: %s" % (core.stack_path(stackname),))
        return

    if core.stack_is_active(stackname):
        LOG.info("stack exists") # avoid `on_start` handler
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

def upgrade_v2_troposphere_template_to_v3(template_data):
    """the major version update of troposphere 2.7.1 to 3.0.0 switched string-booleans to plain booleans:
    > Booleans are output instead of string booleans for better interoperability with tools like cfn-lint.
    - https://github.com/cloudtools/troposphere/releases/tag/3.0.0

    this function looks for the strings "true" and "false" and converts them to True and False, emitting
    a warning if it finds any.

    I don't know if there are string-booleans that need to be kept as such."""
    def convert_string_bools(v):
        if v == 'true':
            LOG.warning("found string 'true' in Cloudformation template, converting to boolean True")
            return True
        if v == 'false':
            LOG.warning("found string 'false' in Cloudformation template, converting to boolean False")
            return False
        return v
    return utils.visit(template_data, convert_string_bools)

def _read_template(path_to_template):
    template_data = json.load(open(path_to_template, 'r'))
    template_data = upgrade_v2_troposphere_template_to_v3(template_data)
    return template_data

def read_template(stackname):
    "returns the contents of a cloudformation template as a python data structure"
    return _read_template(os.path.join(config.STACK_DIR, stackname + ".json"))

def outputs_map(stackname):
    """returns a map of a stack's 'Output' keys to their values.
    performs a boto API call."""
    data = core.describe_stack(stackname).meta.data # boto3
    if not 'Outputs' in data:
        return {}
    return {o['OutputKey']: o.get('OutputValue') for o in data['Outputs']}

def template_outputs_map(stackname):
    """returns a map of a stack template's 'Output' keys to their values.
    requires a stack to exist on the filesystem."""
    stack = json.load(open(core.stack_path(stackname), 'r'))
    output_map = stack.get('Outputs', [])
    return {output_key: output['Value'] for output_key, output in output_map.items()}

def template_using_elb_v1(stackname):
    "returns `True` if the stack template file is using an ELB v1 (vs an ALB v2)"
    return trop.ELB_TITLE in template_outputs_map(stackname)

def read_output(stackname, key):
    """finds a literal `Output` from a cloudformation template matching given `key`.
    fails hard if expected key not found, or too many keys found.
    performs a boto API call."""
    data = core.describe_stack(stackname).meta.data # boto3
    ensure('Outputs' in data, "Outputs missing: %s" % data)
    selected_outputs = [o for o in data['Outputs'] if o['OutputKey'] == key]
    ensure(selected_outputs, "No outputs found for key %r" % (key,))
    ensure(len(selected_outputs) == 1, "Too many outputs selected for key %r: %s" % (key, selected_outputs))
    ensure('OutputValue' in selected_outputs[0], "Badly formed Output for key %r: %s" % (key, selected_outputs[0]))
    return selected_outputs[0]['OutputValue']

def apply_delta(template, delta):
    for component in delta.plus:
        ensure(component in ["Resources", "Outputs", "Parameters"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.plus[component])
        template[component] = data
    for component in delta.edit:
        ensure(component in ["Resources", "Outputs"], "Template component %s not recognized" % component)
        data = template.get(component, {})
        data.update(delta.edit[component])
        template[component] = data
    for component in delta.minus:
        ensure(component in ["Resources", "Outputs", "Parameters"], "Template component %s not recognized" % component)
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
    with open(output_fname, 'w') as fp:
        fp.write(contents)
    return output_fname

def update_template(stackname, delta):
    if delta.non_empty:
        new_template = _merge_delta(stackname, delta)
        _update_template(stackname, new_template)
    else:
        # attempting to apply an empty change set would result in an error
        LOG.info("Nothing to update on CloudFormation")

def _update_template(stackname, template):
    parameters = []
    pdata = core.project_data_for_stackname(stackname)
    if pdata['aws']['ec2']:
        parameters.append({'ParameterKey': 'KeyName', 'ParameterValue': stackname})
    try:
        conn = core.describe_stack(stackname)
        print(json.dumps(template, indent=4))
        conn.update(TemplateBody=json.dumps(template), Parameters=parameters)
    except botocore.exceptions.ClientError as ex:
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
        if "No updates are to be performed" in err['Message']:
            LOG.info("Stack %s does not need updates on CloudFormation", stackname)
            return
        # ClientError(u'An error occurred (ValidationError) when calling the DescribeStacks operation: Stack with id basebox--1234 does not exist',)
        # e.operation_name == 'DescribeStacks'
        # e.response['Error'] == {'Message': 'Stack with id basebox--1234 does not exist', 'Code': 'ValidationError', 'Type': 'Sender'}
        if ex.operation_name == 'DescribeStacks' and "does not exist" in err['Message']:
            LOG.info("Stack %s does not exist on CloudFormation", stackname)
            return

        LOG.exception(msg, meta['HTTPStatusCode'], err['Code'], err['Message'], meta['RequestId'], extra={'response': ex.response})
        # ll: ClientError: An error occurred (ValidationError) when calling the DeleteStack operation: Stack [arn:aws:cloudformation:us-east-1:512686554592:stack/elife-bot--prod/a0b1af 60-793f-11e8-bd5a-5044763dbb7b] cannot be deleted while in status UPDATE_COMPLETE_CLEANUP_IN_PROGRESS
        raise


def _delete_stack_file(stackname):
    path = os.path.join(config.STACK_DIR, stackname + ".json")
    if os.path.exists(path):
        os.unlink(path)
