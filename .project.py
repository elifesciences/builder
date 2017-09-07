#!/usr/bin/env python
# renders a project's final configuration as YAML
# if run without any arguments, returns a list of known projects
# requires the builder venv
# NOTE: we capture this logic here to avoid dealing with Fabric's noisy output
import sys, os, argparse, json
from functools import partial

# capture params
parser = argparse.ArgumentParser()
parser.add_argument('--env')
parser.add_argument('--formula', action='store_true', default=False)
parser.add_argument('pname', nargs='*')
parser.add_argument('--task', choices=['project-data', 'salt-master-config'], default='project-data')
parser.add_argument('--format', default='yaml')
args = parser.parse_args()

# hide any unimportant logging
import logging
logging.disable(logging.CRITICAL)

# import buildercore
src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)
from buildercore import project, utils, bootstrap

output = None

# specific project, specific task
if args.pname:
    pname = args.pname[0] # multiple projects in future?
    
    if args.task == 'project-data':
        output = project.project_data(pname)

    elif pname == 'master-server' and args.task == 'salt-master-config':
        master_configuration_template = open('etc-salt-master.template', 'r')
        output = bootstrap.expand_master_configuration(master_configuration_template)

# many projects
else:
    if args.formula:
        # only project formulas
        output = project.known_formulas()
    elif args.env: # vagrant/aws
        # only projects that use given environment
        output = project.filtered_projects(lambda pname, pdata: args.env in pdata).keys()
    else:
        # all projects
        output = project.project_list()
    output.sort()

formats = {
    'yaml': utils.yaml_dumps,
    'json': partial(json.dumps, indent=4),
}
if args.format not in formats:
    print 'unknown format: %s' % args.format
    print 'known formats: %s' % formats.keys()
    exit(1)
print formats[args.format](output)
