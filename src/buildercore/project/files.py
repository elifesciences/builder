import os, copy
from os.path import join
from collections import OrderedDict

# from . import core # DONT import core. this module should be relatively independent
from buildercore import utils
from buildercore.decorators import testme
from kids.cache import cache as cached

import logging
LOG = logging.getLogger(__name__)


@testme
def update_project_file(path, value, project_data, project_file):
    # if not project_data:
    #    project_data = utils.ordered_load(open(project_file, 'r'))
    utils.updatein(project_data, path, value, create=True)
    return project_data

@testme
def write_project_file(new_project_data, project_file):
    data = utils.yaml_dumps(new_project_data)
    # this awful bit of code injects two new lines after before each top level element
    lines = []
    for line in data.split('\n'):
        if line and lines and line[0] != " ":
            lines.append("")
            lines.append("")
        lines.append(line)
    # all done. convert back to ordereddict
    open(project_file, 'w').write("\n".join(lines))
    return project_file


#
#
#

@cached
def all_projects(project_file):  # , project_file=config.PROJECT_FILE):
    allp = utils.ordered_load(open(project_file))
    if allp is None:
        return ({}, [])
    assert "defaults" in allp, ("Project file %s is missing a `default` section" % project_file)
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
    utils.deepmerge(global_defaults, default_overrides)

    # exceptions.
    # these values *shouldn't* be merged if they *don't* exist in the project
    aws_excluding = ['rds', 'ext', 'elb', 'cloudfront', 'elasticache']
    excluding = [
        'aws',
        'vagrant',
        'vagrant-alt',
        'aws-alt',
        {'aws': aws_excluding},
    ]
    project_data = copy.deepcopy(global_defaults)
    utils.deepmerge(project_data, project_list[pname], excluding)

    # merge in any per-project overrides
    # DO NOT use exclusions here
    project_overrides = _merge_snippets(pname, snippets)
    utils.deepmerge(project_data, project_overrides)

    # handle the alternate configurations
    for altname, altdata in project_data.get('aws-alt', {}).items():
        # take project's *current aws state*,
        project_aws = copy.deepcopy(project_data['aws'])

        # merge in any overrides
        utils.deepmerge(project_aws, altdata)

        # merge this over top of original aws defaults
        orig_defaults = copy.deepcopy(global_defaults['aws'])

        utils.deepmerge(orig_defaults, project_aws, aws_excluding)
        project_data['aws-alt'][altname] = orig_defaults

    for altname, altdata in project_data.get('vagrant-alt', {}).items():
        orig = copy.deepcopy(altdata)
        utils.deepmerge(altdata, project_data['vagrant'])
        utils.deepmerge(altdata, orig)

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
        # this call fails non-deterministically in build, debugging it

        try:
            os.mkdir(path)
        except BaseException:
            import subprocess
            print "Debugging os.mkdir(path) failure"
            print subprocess.check_output(["ls", "-l", os.path.dirname(path)], stderr=subprocess.STDOUT)
            raise
    return path

def find_snippets(project_file):
    path = project_dir_path(project_file)
    fnames = os.listdir(path)
    fnames = filter(lambda fname: not fname.startswith('.'), fnames)
    fnames = filter(lambda fname: fname.endswith('.yaml'), fnames)
    path_list = map(lambda fname: join(path, fname), fnames)
    path_list = sorted(filter(os.path.isfile, path_list))
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
