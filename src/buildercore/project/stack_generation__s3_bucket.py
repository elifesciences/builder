import json
import logging
import os
import tempfile

from botocore.exceptions import ClientError

from buildercore import core, utils
from buildercore.project import stack_config as project_config

LOG = logging.getLogger(__name__)

def cache_path(unique_name):
    "returns a path to a temporary file using the given `unique_name`."
    # "/tmp/foo.json"
    return os.path.join(tempfile.gettempdir(), unique_name + ".json")

def cached_output(unique_name):
    "returns the contents of a json cache file for the given `unique_name`, or None if it doesn't exist."
    path = cache_path(unique_name)
    if not os.path.exists(path):
        LOG.info("cache miss, path not found: %s", path)
        return None
    else:
        LOG.debug("cache hit, path found: %s", path)
        with open(path) as fh:
            return json.load(fh)

def cache(data, unique_name):
    """writes given `data` as JSON to a temporary file using `unique_name`.
    returns path to cached data."""
    path = cache_path(unique_name)
    with open(path, 'w') as fh:
        fh.write(utils.json_dumps(data, indent=4))
    return path

# ---

def _s3_bucket_data(name):
    """returns a dict of s3 bucket data for the given `name` from AWS
    does minimal processing, it's job is to capture side effects."""
    client = core.boto_client('s3', region=None)
    versioning_resp = client.get_bucket_versioning(Bucket=name)
    try:
        tag_resp = client.get_bucket_tagging(Bucket=name)
    except ClientError:
        tag_resp = {}
    return {
        'versioning': versioning_resp.get('Status'),
        'tag-list': tag_resp.get('TagSet') or []
    }

def _s3_bucket_list():
    """returns a list of s3 buckets from AWS.
    does minimal processing, it's job is to capture side effects."""
    bucket_list = core.boto_client('s3').list_buckets().get('Buckets') or []
    return {
        'bucket-list': bucket_list
    }

def regenerate_resource(old_resource):
    """fetches and processes the data from AWS for the given `old_resource`.
    each resource must contain the neccessary data to fetch any updates."""
    name = old_resource['name']
    output = cached_output(name)
    if not output:
        output = _s3_bucket_data(name)
        cache(output, name)

    old_resource['versioning'] = output['versioning'] == 'Enabled'

    tag_list = [(t['Key'], t['Value']) for t in output['tag-list']]
    tag_list = dict(sorted(tag_list, key=lambda x: x[0]))
    old_resource['tag-list'] = tag_list or {}

    return old_resource

def generate_stack(config_path):
    """generates 'stacks' from s3 buckets.
    each stack has a single s3 bucket resource.
    the name of each stack if the name of the s3 bucket.
    buckets that have AWS CloudFormation tagging are excluded."""
    stack_map = project_config.read_stack_file(config_path)
    defaults, _ = project_config.parse_stack_map(stack_map)

    name = 'aws-bucket-list'
    output = cached_output(name)
    if not output:
        output = _s3_bucket_list()
        cache(output, name)

    bucket_list = output['bucket-list']

    def s3_resource(bucket):
        return {'name': bucket['Name'],
                'meta': {
                    'type': 's3-bucket'},
                'created': bucket['CreationDate']}

    resource_item_list = [s3_resource(bucket) for bucket in bucket_list]
    resource_item_list = [regenerate_resource(resource) for resource in resource_item_list]

    def s3_stack(resource):
        "return a top-level 'stack' using the resource's name as the stack's ID."
        return {resource['name']: {'description': None,
                                   'resource-list': [resource]}}

    s3_stack_list = [s3_stack(resource) for resource in resource_item_list]

    def not_cloudformation_tagged(stack):
        tag = 'aws:cloudformation:stack-id'
        # {"foo": {"meta": ..., "resource-list": ...}} => {"meta": ..., "resource-list": ...}
        stack_data = next(iter(stack.values()))
        for resource in stack_data['resource-list']:
            if tag in resource.get('tag-list', {}):
                LOG.warning("excluding %r, it belongs to: %s",
                            resource['name'], resource['tag-list']['aws:cloudformation:stack-name'])
                return False
        return True

    s3_stack_list = filter(not_cloudformation_tagged, s3_stack_list)

    return list(s3_stack_list)
