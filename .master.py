#!/usr/bin/env python
# renders a master-server's configuration as YAML
# only argument is the template etc-salt-master file
import sys
from buildercore import bootstrap, project

all_formulas = project.known_formulas()
master_configuration_template=open(sys.argv[1], 'r')
print bootstrap.render_master_configuration(master_configuration_template, all_formulas).getvalue()
