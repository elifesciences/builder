from unittest import mock
from . import base
from buildercore import utils
from buildercore.project import stack_config, stack_generation

def test_generate_stacks(tempdir, datadir):
    "stack config can be generated for a given type and config path"
    resource_type = 's3-bucket'
    config_path = base.copy_fixture("stacks/s3-stacks.yaml", datadir)

    bucket_list_fixture = base.json_fixture("stacks/data/aws-bucket-list.json")
    with mock.patch("buildercore.project.stack_generation._s3_bucket_list", return_value=bucket_list_fixture):
        fixture_list = [
            base.json_fixture("stacks/data/s3-bucket-foo.json"),
            base.json_fixture("stacks/data/s3-bucket-bar.json"),
        ]
        with mock.patch("buildercore.project.stack_generation._s3_bucket_data", side_effect=fixture_list):
            stack_generation.generate_stacks(resource_type, config_path)

    # print('wrote',open(config_path,'r').read())

    actual = stack_config.all_stack_data(config_path)
    actual = utils.remove_ordereddict(actual)

    import pprint
    pprint.pprint(actual)

    expected = \
        {'bar': {'description': None,
                 'meta': {'type': 'stack', 'version': 0},
                 'resource-list': [{'description': None,
                                    'meta': {'description': 'an AWS S3 bucket',
                                             'type': 's3-bucket',
                                             'version': 0},
                                    'name': 'bar',
                                    'read-only': {'created': '2015-02-02T20:45:52+00:00',
                                                  'region': None},
                                    'tag-list': {},
                                    'versioning': True}]},
         'foo': {'description': None,
                 'meta': {'type': 'stack', 'version': 0},
                 'resource-list': [{'description': None,
                                    'meta': {'description': 'an AWS S3 bucket',
                                             'type': 's3-bucket',
                                             'version': 0},
                                    'name': 'foo',
                                    'read-only': {'created': '2013-01-01T12:46:40+00:00',
                                                  'region': None},
                                    'tag-list': {'Foo': 'Oof'},
                                    'versioning': False}]}}

    assert actual == expected
