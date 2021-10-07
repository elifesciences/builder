from buildercore import bluegreen_v2
from mock import patch, MagicMock

NODE_PARAMS = {
    'key_filename': './dummy1--test.pem',
    'nodes': {
        'i-10000001': 1,
        'i-10000002': 2,
    },
    'public_ips': {
        'i-10000001': '127.0.0.1',
        'i-10000002': '127.0.0.2',
    },
    'stackname': 'dummy1--test',
    'user': 'ubuntu'
}

TARGET_HEALTH = {
    'TargetHealthDescriptions': [
        {
            'Target': {
                'Id': 'i-10000001',
                'Port': 80,
                'AvailabilityZone': 'us-east-1'
            },
            'HealthCheckPort': '80',
            'TargetHealth': {
                'State': 'healthy',
            }
        },

        {
            'Target': {
                'Id': 'i-10000002',
                'Port': 443,
                'AvailabilityZone': 'us-east-1'
            },
            'HealthCheckPort': '443',
            'TargetHealth': {
                'State': 'healthy',
            }
        },
    ]
}

TARGET_GROUP_OUTPUT = {'ELBv2TargetGroupHttp80': 'arn--my-target-group'}

def test_divide_by_colour():
    expected = (
        {'key_filename': './dummy1--test.pem',
         'nodes': {
             'i-10000001': 1
         },
         'public_ips': {
             'i-10000001': '127.0.0.1'
         },
         'stackname': 'dummy1--test',
         'user': 'ubuntu'},

        {'key_filename': './dummy1--test.pem',
         'nodes': {
             'i-10000002': 2
         },
         'public_ips': {
             'i-10000002': '127.0.0.2'
         },
         'stackname': 'dummy1--test',
         'user': 'ubuntu'}
    )
    assert bluegreen_v2.divide_by_colour(NODE_PARAMS) == expected

def test_target_group_arn_list():
    expected = ['arn--my-target-group']
    stackname = "journal--with-alb.json"
    with patch('buildercore.cloudformation.outputs_map', return_value=TARGET_GROUP_OUTPUT):
        assert bluegreen_v2._target_group_arn_list(stackname) == expected

def test_target_group_health():
    expected = [
        {
            'Target': {
                'Id': 'i-10000001',
                'Port': 80,
                'AvailabilityZone': 'us-east-1'
            },
            'HealthCheckPort': '80',
            'TargetHealth': {
                'State': 'healthy',
            }
        },

        {
            'Target': {
                'Id': 'i-10000002',
                'Port': 443,
                'AvailabilityZone': 'us-east-1'
            },
            'HealthCheckPort': '443',
            'TargetHealth': {
                'State': 'healthy',
            }
        },
    ]
    stackname = "foo"
    target_group_arn = "arn--my-target-group"
    mock = MagicMock()
    mock.describe_target_health.return_value = TARGET_HEALTH
    with patch('buildercore.bluegreen_v2.conn', return_value=mock):
        assert bluegreen_v2._target_group_health(stackname, target_group_arn) == expected

def test_target_groups():
    expected = {
        'arn--my-target-group': [
            {
                'Target': {
                    'Id': 'i-10000001',
                    'Port': 80,
                    'AvailabilityZone': 'us-east-1'
                },
                'HealthCheckPort': '80',
                'TargetHealth': {
                    'State': 'healthy',
                }
            },

            {
                'Target': {
                    'Id': 'i-10000002',
                    'Port': 443,
                    'AvailabilityZone': 'us-east-1'
                },
                'HealthCheckPort': '443',
                'TargetHealth': {
                    'State': 'healthy',
                }
            },
        ]
    }
    stackname = "foo"
    mock = MagicMock()
    mock.describe_target_health.return_value = TARGET_HEALTH
    with patch('buildercore.bluegreen_v2.conn', return_value=mock):
        with patch('buildercore.cloudformation.outputs_map', return_value=TARGET_GROUP_OUTPUT):
            assert bluegreen_v2._target_groups(stackname) == expected

def test_target_group_nodes():
    stackname = "foo"
    expected = {
        'arn--my-target-group': [
            {'Id': 'i-10000001'},
            {'Id': 'i-10000002'}
        ]
    }
    with patch('buildercore.cloudformation.outputs_map', return_value=TARGET_GROUP_OUTPUT):
        assert bluegreen_v2._target_group_nodes(stackname, NODE_PARAMS) == expected

def test_registered():
    expected = {('i-10000001', 80): True,
                ('i-10000002', 443): True}
    stackname = "foo"
    mock = MagicMock()
    mock.describe_target_health.return_value = TARGET_HEALTH
    with patch('buildercore.bluegreen_v2.conn', return_value=mock):
        with patch('buildercore.cloudformation.outputs_map', return_value=TARGET_GROUP_OUTPUT):
            assert bluegreen_v2._registered(stackname, NODE_PARAMS) == expected
