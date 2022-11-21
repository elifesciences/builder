'''logic to generate and refresh the configuration of stacks and their list of resources.

'''
from pprint import pprint as _pprint
import os, tempfile, json
from buildercore import core, utils
from buildercore.utils import ensure
from buildercore.project import stack_config as project_config
from botocore.exceptions import ClientError

import logging

LOG = logging.getLogger(__name__)

# ---

def pprint(*args):
    list(map(_pprint, args))

def cache_path(unique_name):
    # "/tmp/foo.json"
    return os.path.join(tempfile.gettempdir(), unique_name + ".json")

def cached_output(unique_name):
    "returns the contents of a json cache file for the given `unique_name`, or None if it doesn't exist."
    path = cache_path(unique_name)
    if not os.path.exists(path):
        LOG.info("cache miss, path not found: %s", path)
    else:
        LOG.debug("cache hit, path found: %s", path)
        return json.load(open(path, 'r'))

def cache_output(output, unique_name):
    open(cache_path(unique_name), 'w').write(utils.json_dumps(output, indent=4))

# ---

def _s3_bucket_data(name):
    """talks to AWS and returns a dict of s3 bucket data for the given `name`.
    does minimal processing, it's job is to capture side effects."""
    #assert False
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
    """talks to AWS and returns a list of s3 buckets.
    does minimal processing, it's job is to capture side effects."""
    #assert False
    bucket_list = core.boto_client('s3').list_buckets().get('Buckets') or []
    #s3 = core.boto_resource('s3')
    #bucket_list = list(map(lambda b: b.meta.data, s3.buckets.limit(10)))
    return {
        'Buckets': bucket_list
    }

def _regenerate_resource__s3_bucket(old_resource):
    """fetches and processes the data from AWS for the given `old_resource`.
    each resource must contain the neccessary data to fetch any updates."""
    name = old_resource['name']
    output = cached_output(name)
    if not output:
        output = _s3_bucket_data(name)
        cache_output(output, name)

    old_resource['versioning'] = output['versioning'] == 'Enabled'

    tag_list = [(t['Key'], t['Value']) for t in output['tag-list']]
    tag_list = {k: v for k, v in sorted(tag_list, key=lambda x: x[0])}
    old_resource['tag-list'] = tag_list or {}

    return old_resource

def _regenerate_resource(resource):
    dispatch = {
        's3-bucket': _regenerate_resource__s3_bucket,
    }
    dispatch_fn = dispatch[resource['meta']['type']]
    return dispatch_fn(resource)

def regenerate(stackname, config_path):
    """update each of the resources for the given `stackname` in stack config file `config_path`."""
    stack_map = project_config.read_stack_file(config_path)
    defaults, stack_map = project_config.parse_stack_map(stack_map)
    ensure(stackname in stack_map, "stack %r not found. known stacks: %s" % (stackname, ", ".join(stack_map.keys())))
    stack = stack_map[stackname]

    new_resource_list = [_regenerate_resource(resource) for resource in stack['resource-list']]
    stack['resource-list'] = new_resource_list
    project_config.write_stack_file_updates({stackname: stack}, config_path)

def _generate_stack__s3(config_path):
    stack_map = project_config.read_stack_file(config_path)
    defaults, _ = project_config.parse_stack_map(stack_map)

    name = 'aws-bucket-list'
    output = cached_output(name)
    if not output:
        output = _s3_bucket_list()
        cache_output(output, name)

    bucket_list = output['Buckets']

    def s3_resource(bucket):
        return {'name': bucket['Name'],
                'meta': {
                    'type': 's3-bucket'},
                'read-only': {
                    'created': bucket['CreationDate']}}

    resource_item_list = [s3_resource(bucket) for bucket in bucket_list]
    resource_item_list = [_regenerate_resource(resource) for resource in resource_item_list]

    def s3_stack(resource):
        "return a top-level 'stack' using the resource's name as the stack's ID."
        return {resource['name']: {'description': None,
                                   'resource-list': [resource]}}

    s3_stack_list = [s3_stack(resource) for resource in resource_item_list]

    def not_cloudformation_tagged(stack):
        tag = 'aws:cloudformation:stack-id'
        # {"foo": {"meta": ..., "resource-list": ...}} => {"meta": ..., "resource-list": ...}
        stack_data = list(stack.values())[0]
        for resource in stack_data['resource-list']:
            if tag in resource.get('tag-list', {}):
                LOG.warning("excluding %r, it belongs to: %s" %
                            (resource['name'], resource['tag-list']['aws:cloudformation:stack-name']))
                return False
        return True

    s3_stack_list = filter(not_cloudformation_tagged, s3_stack_list)

    return list(s3_stack_list)


# ---

def generate_stacks(resource_type, config_path):
    """generate new stacks with a single resource of the given `resource_type`.
    intended to bulk populate config files."""
    dispatch = {
        's3-bucket': _generate_stack__s3
    }
    ensure(resource_type in dispatch,
           "unsupported resource type %r. supported resource types: %s" % (resource_type, ", ".join(dispatch.keys())))
    ensure(os.path.exists(config_path), "config path %r does not exist" % config_path)

    dispatch_fn = dispatch[resource_type]
    generated_stack_list = dispatch_fn(config_path)

    # sanity check, make sure each generated stack looks like:
    # {"foo-bucket": {"name": "foo-bucket", "meta": {...}, ...}}
    for stack in generated_stack_list:
        ensure(len(stack.keys()) == 1, "bad stack, expected exactly 1 key: %r" % stack)

    # todo: we want to update/replace an existing stack if present.
    # this should preserve any yaml comments

    d = {}
    for g in generated_stack_list:
        d.update(g)

    project_config.write_stack_file_updates(d, config_path)
