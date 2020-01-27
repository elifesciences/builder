import os
from buildercore.command import local, settings
from buildercore import project, utils as core_utils, core, cfngen, config
from buildercore.utils import ensure
from decorators import requires_project, echo_output
import utils

@requires_project
@echo_output
def data(pname, output_format=None):
    "given a project name, returns the fully realized project description data."
    formatters = {
        'json': core_utils.json_dumps,
        'yaml': core_utils.yaml_dumps,
        # None: core_utils.remove_ordereddict
        None: lambda v: v
    }
    ensure(output_format in formatters.keys(), "unknown output format %r" % output_format)
    formatter = formatters.get(output_format)
    return formatter(project.project_data(pname))

@requires_project
@echo_output
def context(pname, output_format=None):
    formatters = {
        'json': core_utils.json_dumps,
        'yaml': core_utils.yaml_dumps,
        # None: core_utils.remove_ordereddict
        None: lambda v: v
    }
    ensure(output_format in formatters.keys(), "unknown output format %r" % output_format)
    formatter = formatters.get(output_format)
    return formatter(cfngen.build_context(pname, stackname=core.mk_stackname(pname, "test")))

def _clone_project_formula(furl):
    """clones a formula to `./cloned-projects/$formulaname`, if it doesn't already exist.
    if it does exist, it attempts to update it with a `git pull`."""
    destination = config.CLONED_PROJECT_FORMULA_DIR # /path/to/builder/cloned-projects
    fpath = os.path.join(destination, os.path.basename(furl)) # /path/to/builder/cloned-projects/builder-base-formula

    cmd = "cd %s; git clone %s" % (destination, furl)
    if os.path.exists(fpath):
        cmd = "cd %s; git pull" % (fpath,)
    with settings(warn_only=True):
        local(cmd)

@requires_project
def clone_project_formulas(pname):
    "clones the formulas and formula dependencies of a specific project."
    [_clone_project_formula(furl) for furl in project.project_formulas()[pname]]

def clone_all_project_formulas():
    """clones the formulas and formula dependencies of all known projects.
    does not attempt to clone a repository more than once."""
    [_clone_project_formula(furl) for furl in project.known_formulas()]

def new():
    "creates a new project formula from a template"
    pname = utils.uin('project name')
    local('./scripts/new-project.sh %s' % pname)
