from pprint import pformat
import utils
from decorators import requires_aws_stack
from buildercore import core, cfngen, context_handler
from buildercore.utils import json_dumps, subdict, lu, shallow_flatten
import logging
LOG = logging.getLogger(__name__)

def success(msg=None):
    if msg:
        print(msg)
    return True

def problem(description, solution, details=None):
    return (description, solution, details)

def title(t):
    print("## %s\n" % t)

#


SEP = "%s\n" % ("-" * 20,)


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
    title("fix_infrastructure")
    disclaimer = """this task performs checks and suggests fixes.

it does *not* modify infrastructure.

ctrl-c will safely quit this task."""

    # see: `buildercore.config.BUILDER_NON_INTERACTIVE` for skipping confirmation prompts
    utils.confirm(disclaimer)
    return success()

def _stack_diff(stackname):
    title("builder drift check")
    context, delta, current_context = cfngen.regenerate_stack(stackname)
    if any([delta.plus['Outputs'], delta.plus['Parameters'], delta.plus['Resources'],
            delta.edit['Outputs'], delta.edit['Resources'],
            delta.minus['Outputs'], delta.minus['Parameters'], delta.minus['Resources']]):
        description = "builder has found a difference between what was once generated and what is being generated now."
        solution = "./bldr update_infrastructure:%s" % (stackname,)
        return problem(description, solution)
    return success()

def _aws_drift(stackname):
    title('AWS drift check')
    drift_result = core.drift_check(stackname)
    if drift_result:
        description = 'AWS thinks this stack has drifted.'
        details = json_dumps(drift_result, dangerous=True, indent=4)
        solution = "./bldr update_infrastructure:%s" % stackname
        return problem(description, solution, details)
    return success()

def _dns_check(stackname, context):
    title('ec2 DNS')
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

    conn = core.boto_conn(stackname, 'route53', client=True)
    paginator = conn.get_paginator('list_hosted_zones')
    hosted_zone_list = shallow_flatten([page['HostedZones'] for page in paginator.paginate()])
    hosted_zone_map = {z['Name']: z['Id'] for z in hosted_zone_list}

    num_nodes = lu(context, 'project.aws.ec2.cluster-size', default=1)
    if 'ext_node_hostname' in domain_map:
        if num_nodes > 1:
            domain_map.update({"node-%s" % i: domain_map['ext_node_hostname'] % i for i in range(1, num_nodes + 1)})
        del domain_map['ext_node_hostname']

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
        paginator = conn.get_paginator('list_resource_record_sets')
        results = shallow_flatten([page['ResourceRecordSets'] for page in paginator.paginate(HostedZoneId=zone_id)])
        record_map[zone_id] = results
        return results

    def find_records(dns):
        dnsd = dns + '.'
        records = get_records(dns)
        type_list = ['A', 'CNAME']
        return [r for r in records if r['Name'] == dnsd and r['Type'] in type_list]

    def check_record(label, dns):
        print('* checking %r' % dns)
        records = find_records(dns)
        if not records:
            description = 'record %r (%r) not found in Route53' % (dns, label)
            details = "records found: %s" % (pformat(records),)
            solution = './bldr update_dns:%s' % (stackname,)
            return problem(description, solution, details)

    results = []
    for label, dns in domain_map.items():
        if isinstance(dns, str):
            _results = check_record(label, dns)
            if _results:
                results.append(_results)

        elif isinstance(dns, list):
            for subdns in dns:
                _results = check_record(label, subdns)
                if _results:
                    results.append(_results)

    return success() if not results else results

# ---

def format_problem(problem_triple):
    description, solution, details = problem_triple
    if details:
        return "problem:  %s\n   solution: %s\n   details:  %s" % (description, solution, details)
    return "problem:  %s\n   solution: %s" % (description, solution)

def print_problem_list(problem_list):
    title("report")
    formatted_problem_list = ["%s. %s" % (i + 1, format_problem(problem)) for i, problem in enumerate(problem_list)]
    print("\n\n".join(formatted_problem_list))

@requires_aws_stack
def fix_infrastructure(stackname):
    """like `update_infrastructure`, but the emphasis is not on changing/upgrading
    infrastructure but correcting any infrastructure drift and *hopefully* fixing and
    problems. Fix is not guaranteed.

    Some actions are a given and cannot be skipped.

    This drift may go undetected by `update_infrastructure`."""

    problems = []

    def check(result):
        "a check returns True on success, False on skip and a string or list of strings for problems."
        if result is False:
            pass # skipped
        if result is True:
            pass # successful
        if isinstance(result, tuple):
            problems.append(result) # single error
        if isinstance(result, list):
            problems.extend(result) # many errors
        print(SEP)

    check(_disclaimer())

    check(_stack_diff(stackname))

    check(_aws_drift(stackname))

    # context should be available from disk after diff check
    context = context_handler._load_context_from_disk(stackname)
    has_ec2 = _has_nodes(context)
    #has_elb = _has_elb(context)

    # the original problem was that another instance had 'stolen' the DNS records of the journal--prod instance.
    # update_infrastructure failed because nothing looked out of place.
    # so we check the *expected* DNS records against the actual ones.
    check(has_ec2 and _dns_check(stackname, context))

    #check(has_ec2 and _nodes_running(stackname, context))

    # todo: buildvars, ...

    if problems:
        print_problem_list(problems)
    else:
        print('no problems detected')
