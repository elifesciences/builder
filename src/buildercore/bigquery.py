from . import config
import logging
from os.path import join

LOG = logging.getLogger(__name__)

def schema_path(stackname, schema_name):
    """returns absolute path to the local `schema_name` schema file.
    if path begins with './', the file is considered relative to the project root"""
    if schema_name.startswith('./'):
        # "./foo/bar.json => "/path/to/builder/foo/bar.json"
        return join(config.PROJECT_PATH, schema_name)
    # "bar.json" => "/path/to/builder/.cfn/bigquery-schema/foo--prod/bar.json"
    return join(config.BIGQUERY_SCHEMA_DIR, stackname, schema_name)
