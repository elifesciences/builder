"""`stack.py` is the interface to the new resource description and wrangling logic.

`stackcore/*.py` is where all of the non-interface stack wrangling logic lives.

This separation is to reduce any further complexity in `buildercore/*` which is entirely
orientated around the current resource description and data structures.

We have:

* 'stack data files', yaml files containing 'stacks', descriptions of groups of resources.
  - list_stack_data_files
  - generate_stack_data_files

* 'stack data', individual descriptions of groups of resources within stack data files.
  - list_stack_data

* 'stack map' or 'stack', interpolated resource description, merged with defaults, etc.
  - a 'stackname' is literally `$interpolatedstackdata.name`

"""
from pprint import pformat
from stackcore import project
import stackcore.terraform
from stackcore.project import stack_generation # TODO: rename stackfile_generation ?
from decorators import format_output, requires_stack_config
import utils
import buildercore.config
import logging

LOG = logging.getLogger(__name__)

# 'stack data file' operations

@format_output()
def list_stack_data_files():
    """prints the list of known stack data files.
    these paths are configured in your `settings.yaml` file."""
    return buildercore.config.STACKS_PATH_LIST

def generate_stack_data_file(resource_type, config_path):
    """generate new stack data file with a single `resource_type`.
    intended to bulk populate and update stack data files."""
    try:
        stack_generation.generate_stacks(resource_type, config_path)
    except AssertionError as ae:
        raise utils.TaskExit(ae)

# 'stack' operations
# these operate on the interpolated stack data and require the
# reading+parsing+merging of stack data files.
    
@format_output()
def list_stack_data(include_resources=False):
    """prints the name of all known stacks.
    use `include_resources=True` to also display each stack's list of resources."""
    include_resources = utils.strtobool(include_resources)
    stack_map = project.stack_map()
    if include_resources:
        retval = []
        for stackname, stackdata in stack_map.items():
            retval.append({stackname: [r['meta']['type'] for r in stackdata['resource-list']]})
        return retval
    return list(stack_map.keys())

@format_output()
@requires_stack_config
def stack_data(stackname):
    "prints the detailed stack data for the given `stackname`"
    return project.stack(stackname)

# probably works, but the workflow right now is:
# 1. generate stack data file
# 2. generate it again to see changes
#
# changes to individual stacks happens via terraform.
#def regenerate_stack(stackname):
#    """pulls changes for the list of resources for the given `stackname`."""
#    stack = stack_config(stackname)
#    config_path = stack['meta']['path']
#    print('this file may be modified:', config_path)
#    stack_generation.regenerate(stackname, config_path)

def update_infrastructure(stackname):
    """like `cfn.update_infrastructure`, but for stacks."""

    context = stackcore.context.build(stackname, project.stack(stackname))
    delta = stackcore.terraform.generate_delta(context)

    LOG.info("Create: %s", pformat(delta.plus))
    LOG.info("Update: %s", pformat(delta.edit))
    LOG.info("Delete: %s", pformat(delta.minus))
    LOG.info("Terraform delta: %s", delta.terraform)

    utils.confirm('Confirming changes to Terraform template?')

    #stackcore.terraform.update(stackname)
