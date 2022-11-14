import os
from buildercore.command import local, settings
from buildercore import project, core, cfngen, config
from decorators import requires_project, format_output
import utils

@requires_project
@format_output('yaml')
def data(pname, output_format=None):
    "given a project name, returns the fully realized project description data."
    return project.project_data(pname)

# todo: candidate for deletion
@requires_project
@format_output('python')
def context(pname, output_format=None):
    """generates dummy context data for the given project `pname`.
    optionally `output_format` will print context in `json` or `yaml`."""
    return cfngen.build_context(pname, stackname=core.mk_stackname(pname, "test"))

def _clone_project_formula(furl):
    """clones a formula to `./cloned-projects/$formulaname`, if it doesn't already exist.
    if it does exist, it attempts to update it with a `git pull`."""
    destination = config.CLONED_PROJECT_FORMULA_PATH # /path/to/builder/cloned-projects
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
    """clones formulas and formula dependencies of all known projects.
    does not attempt to clone a repository more than once."""
    [_clone_project_formula(furl) for furl in project.known_formulas()]

def new():
    "creates a new project formula from a template"
    pname = utils.uin('project name')
    local('./scripts/new-project.sh %s' % pname)
