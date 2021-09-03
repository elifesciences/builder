from pprint import pformat
import utils
from utils import TaskExit
from buildercore import core, cfngen, checks, context_handler
from buildercore.utils import ensure, json_dumps, subdict, lu, shallow_flatten

import logging
LOG = logging.getLogger(__name__)


SEP = "%s\n" % ("-" * 20,)

def _print_diff(stackname):
    print('looking for differences')
    context, delta, current_context = cfngen.regenerate_stack(stackname)
    LOG.info("Create: %s", pformat(delta.plus))
    LOG.info("Update: %s", pformat(delta.edit))
    LOG.info("Delete: %s", pformat(delta.minus))
    LOG.info("Terraform delta: %s", delta.terraform)
    print(SEP)


def _has_nodes(context):
    if not 'ec2' in context:
        # very old stack, canned response
        return True

    if isinstance(context['ec2'], bool):
        # no ec2 instances or an instance whose buildvars haven't been updated.
        # either way, the value here can be used as-is
        return context['ec2']

    return True

def _has_elb(context):
    return _has_nodes(context) and context['ec2']['cluster-size'] > 1

# ---


def ec2_node_summary(ec2):
    data = ec2.meta.data
    keys = [
        'InstanceId',
        'InstanceType',
        'PublicIpAddress',
        'PrivateIpAddress',
        'State',
    ]
    return subdict(data, keys)

# ---


def _disclaimer():
    disclaimer = SEP + """this task attempts some basic fixes.

it cannot guarantee anything will actually be fixed.

*checks* will be made and then *fixes* attempted.

each fix is preceeded by an explanation and a prompt.

ctrl-c at any of these prompts will safely quit this task.

ctrl-c *during* a fix may cause new problems.\n""" + SEP

    # see: `buildercore.config.BUILDER_NON_INTERACTIVE` for skipping confirmation prompts
    utils.confirm(disclaimer)
    print(SEP)

def _check_stack_exists(stackname):
    print('checking %r even exists' % stackname)
    ensure(checks.stack_exists(stackname), "stack not found, cannot continue", TaskExit)
    print('stack found.')
    print(SEP)

def _drift_check(stackname):
    print('using AWS drift checking feature')
    drift_result = core.drift_check(stackname)
    if not drift_result:
        print("no drift detected for stack")
    else:
        print('AWS thinks this stack has drifted:')
        print(json_dumps(drift_result, dangerous=True, indent=4))
    print(SEP)

def _node_check(stackname):
    print('checking EC2 nodes')
    instance_list = core.find_ec2_instances(stackname, allow_empty=True)
    print('%s nodes found, fetching their details' % len(instance_list))
    [print(pformat(ec2_node_summary(ec2))) for ec2 in instance_list]
    print(SEP)

def _dns_check(stackname, context):
    print('checking ec2 DNS')
    keys = [
        'ext_node_hostname', # "prod--lax--%s.elifesciences.org"
        'full_hostname', # "prod--lax.elifesciences.org", "prod--journal.elifesciences.org"
        'project_hostname', # "lax.elifesciences.org", "journal.elifesciences.org"
    ]
    domain_map = subdict(context, keys)

    # these don't appear in Route53
    #domain_map['cloudfront'] = (context.get('cloudfront') or {}).get('subdomains', [])
    domain_map['fastly'] = (context.get('fastly') or {}).get('subdomains', [])

    # this should only appear if ...
    if context['instance_id'] != 'prod':
        del domain_map['project_hostname']

    # {'cloudfront': ['placeholder2-prod-journal.elifesciences.org',
    #                'www.elifesciences.org',
    #                'elife.elifesciences.org',
    #                'prod.elifesciences.org'],
    # 'ext_node_hostname': 'prod--journal--%s.elifesciences.org',
    # 'fastly': ['prod--cdn-journal.elifesciences.org',
    #            'placeholder-prod-journal.elifesciences.org',
    #            'elifesciences.org'],
    # 'full_hostname': 'prod--journal.elifesciences.org',
    # 'project_hostname': 'journal.elifesciences.org'}
    # print(pformat(domain_map))

    #paginator = core.boto_client('route53', region).get_paginator('list_hosted_zones')
    conn = core.boto_conn(stackname, 'route53', client=True)
    paginator = conn.get_paginator('list_hosted_zones')
    hosted_zone_list = shallow_flatten([page['HostedZones'] for page in paginator.paginate()])
    hosted_zone_map = {z['Name']: z['Id'] for z in hosted_zone_list}

    num_nodes = lu(context, 'project.aws.ec2.cluster-size', default=1)
    if num_nodes > 1:
        domain_map.update({"node-%s" % i: domain_map['ext_node_hostname'] % i for i in range(1, num_nodes + 1)})
    del domain_map['ext_node_hostname']

    # print(pformat(hosted_zone_map))

    def hosted_zone_id(dns):
        bits = dns.split('.')
        if len(bits) == 3:
            name = '.'.join(bits[1:]) + '.'
        else:
            name = dns + '.'
        return hosted_zone_map[name]

    record_map = {}

    def get_records(dns):
        zone_id = hosted_zone_id(dns)
        if zone_id in record_map:
            return record_map[zone_id]
        #results = conn.list_resource_record_sets(HostedZoneId=zone_id)['ResourceRecordSets']
        paginator = conn.get_paginator('list_resource_record_sets')
        results = shallow_flatten([page['ResourceRecordSets'] for page in paginator.paginate(HostedZoneId=zone_id)])
        record_map[zone_id] = results
        return results

    def find_records(dns):
        dnsd = dns + '.'
        records = get_records(dns)
        type_list = ['A', 'CNAME']
        return [r for r in records if r['Name'] == dnsd and r['Type'] in type_list]

    def print_record(label, dns):
        if not dns: # empty list
            return
        if isinstance(dns, str):
            records = find_records(dns)
            if not records:
                print('record %r (%r) NOT found in Route53' % (dns, label))
                print(pformat(records))
            else:
                print('record %r (%r) FOUND in Route53' % (dns, label))
        if isinstance(dns, list):
            [print_record(label, subdns) for subdns in dns]

    for label, dns in domain_map.items():
        print_record(label, dns)

    # subdomain
    # intdomain
    # fastly.subdomains
    # cloudfront.subdomains
    #
    print(SEP)

def fix_infrastructure(stackname):
    """like `update_infrastructure`, but the emphasis is not on changing/upgrading
    infrastructure but correcting any infrastructure drift and *hopefully* fixing and
    problems. Fix is not guaranteed.

    Some actions are a given and cannot be skipped.

    This drift may go undetected by `update_infrastructure`."""

    _disclaimer()

    _check_stack_exists(stackname)

    _print_diff(stackname)

    _drift_check(stackname)

    # context should be available from disk after diff check
    context = context_handler._load_context_from_disk(stackname)
    has_ec2 = _has_nodes(context)
    #has_elb = _has_elb(context)

    has_ec2 and _node_check(stackname)

    # the original problem was that another instance had 'stolen' the DNS records of the journal--prod instance.
    # update_infrastructure failed because nothing looked out of place.
    # so we check the *expected* DNS records against the actual ones.
    has_ec2 and _dns_check(stackname, context)

    # todo: fix buildvars if exist
    #print('checking ec2 buildvars')
    # print('...')
