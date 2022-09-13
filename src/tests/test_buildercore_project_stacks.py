from . import base
from buildercore.project import stack_config

def test_deepmerge():
    "the simpler deepmerge for stacks "
    case_list = [
        ({}, {}, {}),
        ({"a": "b"}, {"c": "d"}, {"a": "b", "c": "d"}),
        ({"a": "b"}, {"a": "c"}, {"a": "c"}),
        ({"a": {"b": "c"}}, {"a": {"b": "d"}}, {"a": {"b": "d"}}),

        # here is where rules get fuzzy. should lists be merged?
        # should only a set of unique items from both lists exist?
        # this behaviour hasn't been touched yet, so we'll leave it
        # on 'replace' until we need to revisit it.
        ({"a": {"b": [1, 2, 3]}}, {"a": {"b": []}}, {"a": {"b": []}}),

        # same again for merging different types. last one wins.
        ({"a": {"b": [1, 2, 3]}}, {"a": {"b": {}}}, {"a": {"b": {}}}),
    ]
    for a, b, expected in case_list:
        assert stack_config.deep_merge(a, b) == expected

def test_all_stack_data():
    fixture = base.fixture_path("stacks/stacks.yaml")
    actual = stack_config.all_stack_data(fixture)
    expected = {
        "example-stack-identifier": {
            "description": "a description for this example stack of resources\na resource stack is literally a list of things managed by Cloudformation/Terraform\na 'resource' describes some bit of infrastructure \ndefining it here demonstrates that we know about it and have brought it under configuration control\n",
            "meta": {
                "type": "stack",
                "version": 0
            },
            "resource-list": [
                {
                    "meta": {
                        "description": "an instance of an project created by builder and configured in projects/elife.yaml",
                        "type": "builder-project",
                        "version": 0
                    },
                    "read-only": {
                        "created": None,
                        "updated": None
                    },
                    "name": "journal",
                    "instance-id": "prod"
                }
            ]
        }
    }
    assert actual == expected
