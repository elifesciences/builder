from unittest import mock

import pytest
from buildercore import utils
from buildercore.project import stack_config, stack_generation

from . import base


def test_regenerate(tempdir, datadir):
    "a stack can be regenerated with new data from aws"
    config_path = base.copy_fixture("stacks/s3-stacks--populated.yaml", datadir)
    stackname = "foo"
    before = {'description': None,
              'meta': {'path': datadir + '/s3-stacks--populated.yaml',
                       'type': 'stack',
                       'version': 0},
              'resource-list': [
                  {
                      'description': None,
                      'meta': {'description': 'an AWS S3 bucket',
                               'type': 's3-bucket',
                               'version': 0},
                      'name': 'foo',
                      'created': '2013-01-01T12:46:40+00:00',
                      'tag-list': {},
                      'versioning': False}]}
    assert stack_config.stack_data(stackname, config_path) == before

    fixture_list = [
        base.json_fixture("stacks/data/s3-bucket-foo.json"),
    ]
    with mock.patch("buildercore.project.stack_generation__s3_bucket._s3_bucket_data", side_effect=fixture_list):
        stack_generation.regenerate(stackname, config_path)

    after = before
    after['resource-list'][0]['tag-list'] = {'Foo': 'Oof'}

    assert stack_config.stack_data(stackname, config_path) == after

# fixtures not necessarily needed, but if the assertion fails and it goes on to regenerate the
# stack or fetch aws updates, it could contaminate the fixture and test state for later tests.
def test_regenerate__stack_not_found(tempdir, datadir):
    config_path = base.copy_fixture("stacks/s3-stacks--populated.yaml", datadir)
    stackname = "foobar"
    with pytest.raises(AssertionError):
        stack_generation.regenerate(stackname, config_path)

def test_generate_stacks(tempdir, datadir):
    "stack config can be generated for a given type and config path"
    resource_type = 's3-bucket'
    config_path = base.copy_fixture("stacks/s3-stacks.yaml", datadir)

    bucket_list_fixture = base.json_fixture("stacks/data/aws-bucket-list.json")
    with mock.patch("buildercore.project.stack_generation__s3_bucket._s3_bucket_list", return_value=bucket_list_fixture):
        fixture_list = [
            base.json_fixture("stacks/data/s3-bucket-foo.json"),
            base.json_fixture("stacks/data/s3-bucket-bar.json"),
        ]
        with mock.patch("buildercore.project.stack_generation__s3_bucket._s3_bucket_data", side_effect=fixture_list):
            stack_generation.generate_stacks(resource_type, config_path)

    actual = stack_config.all_stack_data(config_path)
    actual = utils.remove_ordereddict(actual)

    expected = \
        {'bar': {'description': None,
                 'meta': {'type': 'stack', 'version': 0,
                          'path': datadir + "/s3-stacks.yaml"},
                 'resource-list': [
                     {'description': None,
                      'meta': {'description': 'an AWS S3 bucket',
                                              'type': 's3-bucket',
                               'version': 0},
                      'name': 'bar',
                      'created': '2015-02-02T20:45:52+00:00',
                      'tag-list': {},
                      'versioning': True}]},
         'foo': {'description': None,
                 'meta': {'type': 'stack', 'version': 0,
                          'path': datadir + "/s3-stacks.yaml"},
                 'resource-list': [
                     {'description': None,
                      'meta': {'description': 'an AWS S3 bucket',
                                              'type': 's3-bucket',
                               'version': 0},
                      'name': 'foo',
                      'created': '2013-01-01T12:46:40+00:00',
                      'tag-list': {'Foo': 'Oof'},
                      'versioning': False}]}}

    assert actual == expected
