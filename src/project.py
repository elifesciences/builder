from fabric.api import task, local
from buildercore import project, utils as core_utils
from buildercore.utils import ensure
from decorators import requires_project, echo_output
import utils

@task
@requires_project
@echo_output
def data(pname, output_format=None):
    "given a project name, returns the fully realized project description data."
    ensure(output_format in [None, 'json', 'yaml'], "unknown output format %r" % output_format)
    formatters = {
        'json': core_utils.json_dumps,
        'yaml': core_utils.ordered_dump,
        None: lambda v: v
    }
    formatter = formatters.get(output_format)
    return formatter(project.project_data(pname))

@task
def new():
    "creates a new project formula"
    pname = utils.uin('project name')
    #assert pname not in project.project_list(), "that project name already exists"
    local('./scripts/new-project.sh %s' % pname)
