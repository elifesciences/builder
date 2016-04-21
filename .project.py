#!/usr/bin/env python
# renders a project's final configuration as YAML
# requires the builder venv
import sys, os
src_dir = os.path.abspath('src')
sys.path.insert(0, src_dir)
from buildercore import core, config, utils
if not len(sys.argv) > 1:
    print 'usage: ./project.py <projectname>'
    exit(1)
pname = sys.argv[1]
try:
    print utils.ordered_dump(core.project_data(pname))
except KeyError:
    print 'no project found'
