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

# CloudFormation is nicely chopped up into:
# * what to add
# * what to modify
# * what to remove
# What we see here is the new Terraform generated.tf file, containing all resources (just Fastly so far).
# We can do a diff with the current one which would already be an improvement, but ultimately the source of truth
# is changing it and running a terraform plan to see proposed changes. We should however roll it back if the user
# doesn't confirm.
class CloudFormationDelta(namedtuple('CloudFormationDelta', ['plus', 'edit', 'minus', 'terraform'])):
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
            self.terraform
        ])
_empty_cloudformation_dictionary = {'Resources': {}, 'Outputs': {}}
CloudFormationDelta.__new__.__defaults__ = (_empty_cloudformation_dictionary, _empty_cloudformation_dictionary, _empty_cloudformation_dictionary, None)
