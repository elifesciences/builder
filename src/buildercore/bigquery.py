from . import config
import os, requests, logging
from os.path import join

LOG = logging.getLogger(__name__)

def local_schema_path(stackname, schema_name):
    "returns a local path to the given `schema_name`"
    # "/.../.cfn/bigquery-schema/elife-data-pipeline--prod/fooschema.json"
    return join(config.BIGQUERY_SCHEMA_DIR, stackname, schema_name)

def fetch_remote_schema(stackname, file_url):
    "downloads a remote file and writes it to the stack's schema directory"
    LOG.info("fetching schema %s" % file_url)
    resp = requests.get(file_url)
    resp.raise_for_status()
    local_file = local_schema_path(stackname, os.path.basename(file_url))
    # a project with multiple schemas at different locations sharing
    # the same filename will result in files getting overwritten.
    with open(local_file, 'wb') as local_file_handle:
        local_file_handle.write(resp.content)
    return local_file

def relative_local_schema_path(_, schema_name):
    "returns a local path to the given `schema_name` when `schema_name` is a path relative to the root of the project"
    return join(config.PROJECT_DIR, schema_name)

def schema_path(stackname, schema_name):
    "returns a local path to the given `schema_name`, downloading it if necessary"
    if schema_name.startswith('https://'):
        return fetch_remote_schema(stackname, schema_name)
    elif schema_name.startswith('./'):
        return relative_local_schema_path(stackname, schema_name)
    return local_schema_path(stackname, schema_name)
