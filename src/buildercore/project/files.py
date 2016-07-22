import os, json, copy
from os.path import join
from functools import wraps
from collections import OrderedDict

#from . import core # DONT import core. this module should be relatively independent
from buildercore import utils, config
from buildercore.utils import unique, first, dictfilter
from buildercore.decorators import osissue, osissuefn, testme

import logging
LOG = logging.getLogger(__name__)


@testme
def update_project_file(path, value, project_data, project_file):
    #if not project_data:
    #    project_data = utils.ordered_load(open(project_file, 'r'))
    utils.updatein(project_data, path, value, create=True)
    return project_data

@testme
def write_project_file(new_project_data, project_file):
    data = utils.ordered_dump(new_project_data)
    # this awful bit of code injects two new lines after before each top level element
    lines = []
    for line in data.split('\n'):
        if line and lines and line[0] != " ":
            lines.append("")
            lines.append("")
        lines.append(line)
    # all done. convert back to ordereddict
    #new_project_data = utils.ordered_load(StringIO("\n".join(lines)))
    open(project_file, 'w').write("\n".join(lines)) #utils.ordered_dump(new_project_data))
    return project_file


#
#
#

@testme
def all_projects(project_file): #, project_file=config.PROJECT_FILE):
    allp = utils.ordered_load(open(project_file))
    assert allp is not None, ("Project file %s seems to be empty" % project_file)
    assert "defaults" in allp, ("Project file %s does not seem to have a `default` key" % project_file)
    defaults = allp["defaults"]
    del allp["defaults"]
    return defaults, allp

#
#
#

def _merge_snippets(pname, snippets):
    snippets = [{}] + snippets # so none of the snippets are mutated
    def mergedefs(snip1, snip2):
        utils.deepmerge(snip1, snip2)
        return snip1
    overrides = reduce(mergedefs, snippets).get(pname, {})
    return overrides

def project_data(pname, project_file, snippets=0xDEADBEEF):
    "does a deep merge of defaults+project data with a few exceptions"

    if snippets == 0xDEADBEEF:
        snippets = find_snippets(project_file)
    
    # merge all snippets providing a 'defaults' key first
    default_overrides = _merge_snippets('defaults', snippets)
    
    global_defaults, project_list = all_projects(project_file)
    
    project_defaults = copy.deepcopy(global_defaults)
    utils.deepmerge(project_defaults, default_overrides)

    project_data = project_defaults
    
    # exceptions.
    # these values *shouldn't* be merged if they *don't* exist in the project
    excluding = ['aws', 'vagrant', 'vagrant-alt', 'aws-alt', {'aws': ['rds', 'ext']}]
    utils.deepmerge(project_data, project_list[pname], excluding)

    # handle the alternate configurations
    for altname, altdata in project_data.get('aws-alt', {}).items():
        # take project's current aws state, merge in overrides, merge over top of original aws defaults
        project_aws = copy.deepcopy(project_data['aws'])
        orig_defaults = copy.deepcopy(global_defaults['aws'])
        utils.deepmerge(project_aws, altdata)
        utils.deepmerge(orig_defaults, project_aws, ['rds', 'ext'])
        project_data['aws-alt'][altname] = orig_defaults

    for altname, altdata in project_data.get('vagrant-alt', {}).items():
        orig = copy.deepcopy(altdata)
        utils.deepmerge(altdata, project_data['vagrant'])
        utils.deepmerge(altdata, orig)

    # merge in any per-project overrides
    project_overrides = _merge_snippets(pname, snippets)
    utils.deepmerge(project_data, project_overrides)
    
    return project_data

def project_file_name(project_file):
    "returns the name of the project file without the extension"
    fname = os.path.splitext(project_file)[0]
    return os.path.basename(fname)

def project_dir_path(project_file):
    # /path/to/elife-builder/project/elife.yaml =>
    # /path/to/elife-builder/project/elife/
    path = join(os.path.dirname(project_file), project_file_name(project_file))
    if not os.path.exists(path):
        os.mkdir(path)
    return path

def find_snippets(project_file):
    path = project_dir_path(project_file)
    path_list = map(lambda fname: join(path, fname), os.listdir(path))
    path_list = filter(os.path.isfile, path_list)
    path_list = filter(lambda p: p.endswith('.yaml'), path_list)
    path_list.sort() # your snippets need to be in a natural ordering
    return map(lambda p: utils.ordered_load(open(p, 'r')), path_list)



#
#
#

def projects_from_file(path_to_file, *args, **kwargs):
    "returns a map of {org => project data} for a given file"
    orgname = project_file_name(path_to_file)
    _, project_list = all_projects(path_to_file)

    pdata = map(lambda pname: project_data(pname, path_to_file), project_list)
    pdata = OrderedDict(zip(project_list, pdata))
    return OrderedDict({orgname: pdata})
