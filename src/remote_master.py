"""
builder is installed on the remote master to keep things configured.

this module contains tasks that help maintain configuration.
"""

import os
from buildercore import utils as core_utils
from fabric.api import local
from buildercore import project
from decorators import mastertask

def install_formula(pname, formula_url):
    if formula_url.startswith("ssh://"):
        formula_url = formula_url[6:]
    return local("/bin/bash /opt/builder/scripts/update-master-formula.sh %s %s" % (pname, formula_url))

def install_update_formula_deps():
    pdata = project.project_data('master-server')
    for dep in pdata.get('formula-dependencies', []):
        # TODO: this is inconsistent as api-dummy-formula could both be present both as
        # - api-dummy (as project main formula)
        # - api-dummy-formula (as dependency)
        name = os.path.basename(dep) # ll: 'some-formula' in 'https://github.com/elifesciences/some-formula
        install_formula(name, dep)

def private_ip():
    cmd = "/sbin/ifconfig eth0 | awk '/inet / { print $2 }' | sed 's/addr://'"
    return str(local(cmd, capture=True))

def private_file_roots():
    return [
        "/opt/builder-private/salt/",
    ]

def basic_file_roots():
    return [
        "/opt/formulas/builder-base-formula/",
    ]

def private_pillar_roots():
    return [
        "/opt/builder-private/pillar",
    ]

def formula_file_roots():
    formula_path = lambda pname: os.path.join("/opt/formulas/", pname, "salt")
    projects = project.projects_with_formulas().keys()
    return map(formula_path, projects)

def refresh_config():
    with open('/etc/salt/master', 'r') as cfgfile:
        cfg = core_utils.ordered_load(cfgfile)
    cfg['file_roots']['base'] = private_file_roots() + formula_file_roots() + basic_file_roots()
    cfg['pillar_roots']['base'] = private_pillar_roots()
    cfg['interface'] = private_ip()

    with open('/etc/salt/master', 'w') as cfgfile:
        core_utils.ordered_dump(cfg, cfgfile)

@mastertask
def refresh():
    # called as part of the update-master.sh script with the 'master' BLDR ROLE
    # shouldn't be called otherwise
    install_update_formula_deps() # builder base
    refresh_config() # rewrite /etc/salt/master yaml
