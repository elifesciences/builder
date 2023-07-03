from moto import mock_route53
from datetime import datetime
from unittest.mock import patch, MagicMock
from pytz import utc
from . import base
from buildercore.core import parse_stackname
from buildercore import core, cfngen, lifecycle


class TestBuildercoreLifecycle(base.BaseCase):
    def setUp(self):
        self.contexts = {}
        self._generate_context('dummy1--test')
        self._generate_context('project-with-rds-only--test')

    @patch('buildercore.lifecycle.wait_for_ec2_steady_state')
    @patch('buildercore.lifecycle._ec2_connection')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_start_a_not_running_ec2_instance(self, load_context, find_ec2_instances, find_rds_instances, ec2_connection, wait_for_ec2_steady_state):
        load_context.return_value = self.contexts['dummy1--test']
        find_ec2_instances.side_effect = [
            [self._ec2_instance('stopped')],
            [self._ec2_instance('running')],
            [self._ec2_instance('running')] # update_dns additional call
        ]

        c = MagicMock()
        c.start_instances = MagicMock()
        ec2_connection.return_value = c
        lifecycle.start('dummy1--test')

    @patch('buildercore.lifecycle.wait_for_ec2_steady_state')
    @patch('buildercore.lifecycle._rds_connection')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_start_a_not_running_rds_instance(self, load_context, find_ec2_instances, find_rds_instances, rds_connection, wait_for_ec2_steady_state):
        load_context.return_value = self.contexts['project-with-rds-only--test']
        find_ec2_instances.return_value = []
        find_rds_instances.side_effect = [
            [self._rds_instance('stopped')],
            [self._rds_instance('available')]
        ]

        c = MagicMock()
        c.start_db_instance = MagicMock()
        rds_connection.return_value = c

        lifecycle.start('project-with-rds-only--test')

    @patch('buildercore.lifecycle.wait_for_ec2_steady_state')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_start_ec2_idempotence(self, load_context, find_ec2_instances, find_rds_instances, wait_for_ec2_steady_state):
        load_context.return_value = self.contexts['dummy1--test']
        find_ec2_instances.return_value = [self._ec2_instance('running')]
        lifecycle.start('dummy1--test')

    @patch('buildercore.lifecycle.wait_for_ec2_steady_state')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_start_rds_idempotence(self, load_context, find_ec2_instances, find_rds_instances, wait_for_ec2_steady_state):
        load_context.return_value = self.contexts['project-with-rds-only--test']
        find_rds_instances.return_value = [self._rds_instance('available')]
        lifecycle.start('project-with-rds-only--test')

    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_ignores_terminated_stacks_that_have_been_replaced_by_a_new_instance(self, load_context, find_ec2_instances):
        load_context.return_value = self.contexts['dummy1--test']
        old = self._ec2_instance('terminated', 'i-123')
        new = self._ec2_instance('running', 'i-456')

        find_ec2_instances.return_value = [old, new]
        self.assertEqual({'i-456': 'running'}, lifecycle._ec2_nodes_states('dummy1--test'))

    @patch('buildercore.lifecycle._stop')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_stops_ec2_instance(self, load_context, find_ec2_instances, find_rds_instances, _stop):
        load_context.return_value = self.contexts['dummy1--test']
        find_ec2_instances.return_value = [self._ec2_instance('running')]
        find_rds_instances.return_value = []
        lifecycle.stop('dummy1--test')

    @patch('buildercore.lifecycle._stop')
    @patch('buildercore.lifecycle.find_rds_instances')
    @patch('buildercore.lifecycle.find_ec2_instances')
    @patch('buildercore.lifecycle.load_context')
    def test_stops_rds_instance(self, load_context, find_ec2_instances, find_rds_instances, _stop):
        load_context.return_value = self.contexts['project-with-rds-only--test']
        find_ec2_instances.return_value = []
        find_rds_instances.return_value = [self._rds_instance('available')]
        lifecycle.stop('project-with-rds-only--test')

    @patch('buildercore.lifecycle._stop')
    @patch('buildercore.lifecycle.find_ec2_instances')
    def test_stops_instances_when_running_for_too_many_minutes(self, find_ec2_instances, _stop):
        find_ec2_instances.return_value = [self._ec2_instance('running', launch_time=datetime(2000, 1, 1, tzinfo=utc))]
        lifecycle.stop_if_running_for('dummy1--test', 30)

    def _generate_context(self, stackname):
        (pname, instance_id) = parse_stackname(stackname)
        context = cfngen.build_context(pname, stackname=stackname)
        self.contexts[stackname] = context

    def _ec2_instance(self, state='running', id='i-456', launch_time=datetime(2017, 1, 1, tzinfo=utc)):
        instance = MagicMock()
        instance.id = id
        state_codes = {'running': 16}
        instance.state = {'Code': state_codes.get(state, -1), 'Name': state} # 'Code' should vary but probably isn't being used
        instance.tags = [{'Key': 'Name', 'Value': 'dummy1--test--1'}]
        instance.launch_time = launch_time
        return instance

    def _rds_instance(self, state='available', id='i-456'):
        instance = {
            'DBInstanceIdentifier': id,
            'DBInstanceStatus': state,
        }
        return instance

@mock_route53
def test_get_create_update_delete_dns_a_record():
    zone_name = "example.org"
    name = "bar--foo.example.org"
    value = "1.2.3.4"

    # set up a dummy hosted zone
    conn = core.boto_client('route53')
    dummy_hosted_zone = conn.create_hosted_zone(Name=zone_name, CallerReference='foo')
    expected_zone_id = dummy_hosted_zone['HostedZone']['Id']

    # ensure empty
    expected_record = None
    expected_name = "bar--foo.example.org."
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

    # create a record
    lifecycle._update_dns_a_record(zone_name, name, value)
    expected_record = {
        "Name": "bar--foo.example.org.",
        "ResourceRecords": [{"Value": "1.2.3.4"}],
        "Type": "A",
        "TTL": 600,
    }
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

    # update a record
    new_value = "4.3.2.1"
    lifecycle._update_dns_a_record(zone_name, name, new_value)
    expected_record = {
        "Name": "bar--foo.example.org.",
        "ResourceRecords": [{"Value": "4.3.2.1"}],
        "Type": "A",
        "TTL": 600,
    }
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

    # update is idempotent
    new_value = "4.3.2.1"
    lifecycle._update_dns_a_record(zone_name, name, new_value)
    expected_record = {
        "Name": "bar--foo.example.org.",
        "ResourceRecords": [{"Value": "4.3.2.1"}],
        "Type": "A",
        "TTL": 600,
    }
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

    # delete a record
    lifecycle._delete_dns_a_record(zone_name, name)
    expected_record = None
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

    # delete an unknown record
    name = "baz--bar.example.org"
    lifecycle._delete_dns_a_record(zone_name, name)
    expected_name = "baz--bar.example.org."
    expected_record = None
    expected = (expected_zone_id, expected_name, expected_record)
    assert lifecycle._get_dns_a_record(zone_name, name) == expected

@mock_route53
def test_get_dns_a_record():
    "boto3 route53 fetching of dns records is a little dodgy and will return similar/adjacent records if we're not really careful"
    zone_name = "example.org"

    # set up a dummy hosted zone
    conn = core.boto_client('route53')
    dummy_hosted_zone = conn.create_hosted_zone(Name=zone_name, CallerReference='foo')
    zone_id = dummy_hosted_zone['HostedZone']['Id']

    # create some records
    record_list = [
        ("foo--bar.example.org", "1.2.3.4"),
        ("foo--baz.example.org", "4.3.2.1"),
    ]
    for name, value in record_list:
        lifecycle._update_dns_a_record(zone_name, name, value)

    # dodgy example 1
    name = "bar.example.org"
    result = conn.list_resource_record_sets(HostedZoneId=zone_id, StartRecordName=name, StartRecordType="A", MaxItems="1")
    expected_dodginess = [{'Name': 'foo--bar.example.org.',
                           'ResourceRecords': [{'Value': '1.2.3.4'}],
                           'TTL': 600,
                           'Type': 'A'}]
    assert result['ResourceRecordSets'] == expected_dodginess

    # dodgy example 2
    name = "example.org"
    result = conn.list_resource_record_sets(HostedZoneId=zone_id, StartRecordName=name, StartRecordType="A", MaxItems="1")
    expected_dodginess = [{'Name': 'example.org.',
                           'ResourceRecords': [{'Value': 'ns-2048.awsdns-64.com'},
                                               {'Value': 'ns-2049.awsdns-65.net'},
                                               {'Value': 'ns-2050.awsdns-66.org'},
                                               {'Value': 'ns-2051.awsdns-67.co.uk'}],
                           'TTL': 172800,
                           'Type': 'NS'}]
    assert result['ResourceRecordSets'] == expected_dodginess

    # safer example 1
    name = "bar.example.org"
    expected_name = "bar.example.org."
    expected_record = None
    expected = (zone_id, expected_name, expected_record)
    result = lifecycle._get_dns_a_record(zone_name, name)
    assert result == expected

    # safer example 2
    name = "example.org"
    expected_name = "example.org."
    expected_record = None
    expected = (zone_id, expected_name, expected_record)
    result = lifecycle._get_dns_a_record(zone_name, name)
    assert result == expected
