#!/usr/bin/env python
# renders a project's final configuration as YAML
# if run without any arguments, returns a list of known projects
# requires the builder venv
import sys, os, argparse, json
from functools import partial

# capture params
parser = argparse.ArgumentParser()
parser.add_argument('--env')
parser.add_argument('pname', nargs='*')
parser.add_argument('--format', default='yaml')
args = parser.parse_args()

# hide any unimportant logging
import logging
logging.disable(logging.CRITICAL)

# import buildercore
src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)
from buildercore import project, utils

# project data
if args.pname:
    pname = args.pname[0] # multiple projects in future?
    output = project.project_data(pname)

# project list
else:
    if args.env: # vagrant/aws
        output = project.filtered_projects(lambda pname, pdata: args.env in pdata).keys()
    else:
        output = project.project_list()
    output.sort()

formats = {
    'yaml': utils.ordered_dump,
    'json': partial(json.dumps, indent=4),
}
if args.format not in formats:
    print 'unknown format: %s' % args.format
    print 'known formats: %s' % formats.keys()
    exit(1)
print formats[args.format](output)
