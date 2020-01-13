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

@requires_project
def clone_project_formulas(pname):
    """clones a project's list of formulas to `cloned-projects/$formulaname`, if it doesn't already exist.
    if it does exist, it attempts to update it with a `git pull`."""
    destination = config.PROJECT_FORMULAS
    pdata = project.project_data(pname)

    formula_url_list = [pdata.get('formula-repo')]
    formula_url_list.extend(pdata.get('formula-dependencies', []))
    formula_url_list = filter(None, formula_url_list)

    for furl in formula_url_list:
        fpath = os.path.join(destination, os.path.basename(furl))
        if os.path.exists(fpath):
            cmd = "cd %s; git pull" % (fpath,)
        else:
            cmd = "cd %s; git clone %s" % (destination, furl)

        with settings(warn_only=True):
            local(cmd)

def clone_all_formulas():
    "clones the formulas and formula dependencies of all known projects"
    for pname in project.project_list():
        clone_project_formulas(pname)

def new():
    "creates a new project formula"
    pname = utils.uin('project name')
    local('./scripts/new-project.sh %s' % pname)
