#!/usr/bin/env python
# lists all formulas used
from buildercore import project

for pname, formula_repo in project.all_formulas().iteritems():
    print "%s,%s" % (pname, formula_repo)
