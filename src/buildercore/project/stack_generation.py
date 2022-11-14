'''logic to generate and refresh the configuration of stacks and their list of resources.

'''

import os, json
from buildercore import core, project
from buildercore.utils import ensure
from buildercore.project import stack_config as project_config
from botocore.exceptions import ClientError

def json_path(unique_name):
    return "/tmp/" + unique_name + ".json"

def json_output(unique_name):
    path = json_path(unique_name)
    if not os.path.exists(path):
        # execute body, assuming json will be written
        print('path not found:', path)
    else:
        print('path FOUND', path)
        return json.load(open(path, 'r'))

def _regenerate_resource__s3_bucket(old_resource):
    "each resource must contain the neccessary information to fetch any updates"

    name = old_resource['name']

    output = json_output(name)
    if not output:
        client = core.boto_client('s3', region=None)

        resp = client.get_bucket_versioning(Bucket=name)
        old_resource['versioning'] = resp.get('Status') == 'Enabled'

        tag_list = {}
        try:
            resp = client.get_bucket_tagging(Bucket=name)
            tag_list = [(t['Key'], t['Value']) for t in resp['TagSet']]
            tag_list = {k: v for k, v in sorted(tag_list, key=lambda x: x[0])}
        except ClientError:
            pass
        old_resource['tag-list'] = tag_list if tag_list else None

        json.dump(old_resource, open(json_path(name), 'w'))
        output = old_resource

    return output

def _regenerate_resource(old_resource):
    dispatch = {
        's3-bucket': _regenerate_resource__s3_bucket,
    }
    dispatch_fn = dispatch.get(old_resource['meta']['type'])
    return dispatch_fn(old_resource)

def regenerate(stackname, config_path):
    """update each of the resources for the given `stackname` in stack config file `config_path`."""
    stack = project.stack_map()[stackname]
    new_resource_list = [_regenerate_resource(resource) for resource in stack['resource-list']]
    stack['resource-list'] = new_resource_list
    project_config.write_stack_file_updates({stackname: stack}, config_path)

def _generate_stack__s3(config_path):
    stack_map = project_config.read_stack_file(config_path)
    defaults, _ = project_config.parse_stack_map(stack_map)

    # todo: paginate!

    aws_resp = json.load(open('/home/luke/dev/python/builder-private-stack-config/bucket-list.json', 'r'))
    bucket_list = aws_resp['Buckets']

    # conn = core.boto_client('s3', None) #defaults['aws']['region'])
    #import json
    #bucket_list = conn.list_buckets()
    #json_bucket_list = json_dumps(bucket_list, indent=4)
    #open('/tmp/bucket-list.json', 'w').write(json_bucket_list)

    def s3_resource(bucket):
        return {'name': bucket['Name'],
                'meta': {
                    'type': 's3-bucket'},
                'read-only': {
                    'created': bucket['CreationDate']}}

    resource_item_list = [s3_resource(bucket) for bucket in bucket_list]
    resource_item_list = [_regenerate_resource(resource) for resource in resource_item_list]

    def s3_stack(resource):
        return {resource['name']: {'description': None,  # 'a helpful description of this bucket',
                                   'resource-list': [{'s3-bucket': resource}]}}

    return [s3_stack(resource) for resource in resource_item_list]


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
    # {"s3-bucket": {"name": "foo-bucket", ...}}
    for stack in generated_stack_list:
        ensure(len(stack.keys()) == 1, "bad stack, expected exactly 1 key: %r" % stack)

    # todo: we want to update/replace an existing stack if present.
    # this should preserve any yaml comments

    d = {}
    for g in generated_stack_list:
        d.update(g)

    project_config.write_stack_file_updates(d, config_path)
