from pprint import pformat
from functools import partial
from os.path import join
from decorators import debugtask
from buildercore import project, utils as core_utils, config

def _hackgibson():
    fixtures_dir = join(config.SRC_PATH, 'tests', 'fixtures')
    config.SETTINGS_FILE = join(fixtures_dir, 'dummy-settings.yaml')
    project.project_map.cache_clear()
    config.app.cache_clear()
    return fixtures_dir

@debugtask
def lst():
    _hackgibson()
    for org, plist in project.org_project_map().items():
        print org
        for project_name in plist:
            print '  ', project_name
        print

@debugtask
def regen(output_format='json'):
    "given a project name, returns the fully realized project description data."
    fixtures_dir = _hackgibson()
    formatters = {
        'json': partial(core_utils.json_dumps, indent=4),
        'yaml': core_utils.yaml_dumps,
        
        'default': lambda v: pformat(core_utils.remove_ordereddict(v))
    }
    formatter = formatters.get(output_format if output_format in formatters else 'default')

    for org, plist in project.org_project_map().items():
        print org
        for pname in plist:
            fix = formatter(project.project_data(pname))
            output_path = join(fixtures_dir, "%s-project.%s" % (pname, output_format))
            with open(output_path, 'w') as fh:
                fh.write(fix)
            print '- wrote', output_path
