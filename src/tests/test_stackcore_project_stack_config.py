from . import base
from stackcore.project import stack_config

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
        # on 'replace' ('override' deepmerge strategy) until we need to revisit it.
        ({"a": {"b": [1, 2, 3]}}, {"a": {"b": []}}, {"a": {"b": []}}),

        # same again for merging different types. last one wins.
        ({"a": {"b": [1, 2, 3]}}, {"a": {"b": {}}}, {"a": {"b": {}}}),
    ]
    for a, b, expected in case_list:
        assert stack_config.deep_merge(a, b) == expected

def test_all_stack_data(datadir):
    "a stack config file can be read and the data returned"
    fixture = base.fixture_path("stacks/stacks.yaml")
    actual = stack_config.all_stack_data(fixture)
    expected = {
        "example-stack-identifier": {
            "description": "a description for this example stack of resources\na resource stack is literally a list of things managed by Cloudformation/Terraform\na 'resource' describes some bit of infrastructure \ndefining it here demonstrates that we know about it and have brought it under configuration control\n",
            "meta": {
                "type": "stack",
                "version": 0,
                "path": fixture
            },
            "random-property": "some-value",
            "resource-list": [
                {
                    "name": "journal",
                    "instance-id": "prod",
                    "meta": {
                        "description": "an instance of an project created by builder and configured in projects/elife.yaml",
                        "type": "builder-project",
                        "version": 0
                    },
                    "updated": None,
                }
            ]
        }
    }
    assert actual == expected

def test__dumps_stack_file():
    "a stack config file can be read, parsed as YAML into Python and dumped back to YAML without changes."
    fixture = base.fixture_path('stacks/stacks.yaml')
    expected = open(fixture, 'r').read()
    config = stack_config.read_stack_file(fixture)
    actual = stack_config._dumps_stack_file(config)
    assert actual == expected

def test__dumps_stack_file__updated_data():
    "a stack config can be read, parsed as YAML into Python, updated with new data and dumped back to YAML with changes preserved."
    fixture = base.fixture_path('stacks/stacks.yaml')
    config = stack_config.read_stack_file(fixture)

    # preserving comments against stacks became too fiddly and time consuming to debug.
    # I've settled for just preserving comments in the 'defaults' section.
    # update = {'example-stack-identifier': {"random-property": "some-new-value"}}
    # config = stack_config.deep_merge(config, update)

    actual = stack_config._dumps_stack_file(config)

    expected = "            instance-id: # project's instance ID"
    assert expected in actual.splitlines()

def test_stack_has_path():
    cases = [
        (None, False),
        ('', False),
        ({}, False),
        ({'foo': 'bar'}, False),
        ({'meta': {'path': 'foo'}}, True)
    ]
    for given, expected in cases:
        assert expected == stack_config.stack_has_path(given)
