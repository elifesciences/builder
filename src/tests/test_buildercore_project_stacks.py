from . import base
#import json
#from os.path import join
from buildercore.project import stack_config

def test_stack():
    fixture = base.fixture_path("stack_config/stacks.yaml")
    expected = {}
    actual = stack_config.all_stacks_data(fixture)

    #import json
    #print(json.dumps(actual, indent=4))

    expected = {
        "example-stack-identifier": {
            "description": "a description for this example stack of resources\na resource stack is literally a list of things managed by Cloudformation/Terraform\na 'resource' describes some bit of infrastructure \ndefining it here demonstrates that we know about it and have brought it under configuration control\n",
            "meta": {
                "type": "stack",
                "version": 0
            },
            "resource-list": [
                {
                    "description": "an instance of an project created by builder and configured in projects/elife.yaml",
                    "meta": {
                        "type": "builder-project",
                        "version": 1,
                        "created": None,
                        "updated": None
                    },
                    "name": None,
                    "instance-id": None,
                    "key": "foo"
                }
            ]
        }
    }
    assert actual == expected
