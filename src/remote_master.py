"""
builder is installed on the remote master to keep things configured.

this module contains tasks that help maintain configuration"""
import os
from buildercore import utils as core_utils
from fabric.api import task, local, lcd, settings, run, sudo, put, get, abort
from buildercore import project
from decorators import echo_output

def install_formula(pname, formula_url):
    return local("/bin/bash /opt/builder/scripts/update-master-formula.sh %s %s" % (pname, formula_url))
    
def install_update_all_project_formulas():
    for pname in project.projects_with_formulas():
        pdata = project.project_data(pname)
        formula_url = pdata['formula-repo']
        install_formula(pname, formula_url)

def install_update_formula_deps():
    pdata = project.project_data('master-server')
    for dep in pdata.get('formula-dependencies', []):
        name = os.path.basename(dep) # ll: 'some-formula' in 'https://github.com/elifesciences/some-formula
        install_formula(name, dep)

@task
@echo_output
def private_ip():
    cmd = "ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://'"
    return str(local(cmd, capture=True))

def basic_file_roots():
    return [
        "/opt/formulas/builder-base-formula/",
        "/srv/salt/",
    ]

def formula_file_roots():
    formula_path = lambda pname: os.path.join("/opt/formulas/", pname, "salt")
    projects = project.projects_with_formulas().keys()
    return map(formula_path, projects)

@task
def refresh_config():
    with open('/etc/salt/master', 'r') as cfgfile:
        cfg = core_utils.ordered_load(cfgfile)
    cfg['file_roots']['base'] = formula_file_roots() + basic_file_roots()
    cfg['interface'] = private_ip()
    
    with open('/etc/salt/master', 'w') as cfgfile:
        core_utils.ordered_dump(cfg, cfgfile)

@task
def refresh():
    install_update_formula_deps()
    install_update_all_project_formulas()
    refresh_config()

