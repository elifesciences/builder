import logging
from pprint import pformat

import utils
from buildercore import cfngen, context_handler, core
from buildercore.utils import json_dumps, lu, shallow_flatten, subdict
from decorators import requires_aws_stack

LOG = logging.getLogger(__name__)
SEP = "%s\n" % ("-" * 20,)

def success(msg=None):
    if msg:
        print(msg)
    return True

def problem(description, solution, details=None):
    return (description, solution, details)

def title(t):
    print("## %s\n" % t)

def _has_nodes(context):
    if 'ec2' not in context:
        LOG.warning("stack has broken context or is extremely old, not looking for ec2")
        return False
    if isinstance(context['ec2'], bool):
        # no ec2 instances or an instance whose buildvars haven't been updated.
        # either way, the value here can be used as-is
        return context['ec2']
    return True

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
    "calls AWS and does a drift check for the given `stackname`. returns `True` if no drift detected."
    title('AWS drift check')
    drift_result = core.drift_check(stackname)
    if drift_result:
        description = 'AWS thinks this stack has drifted.'
        details = json_dumps(drift_result, dangerous=True, indent=4)
        solution = "./bldr update_infrastructure:%s" % stackname
        return problem(description, solution, details)
    return success()

def _dns_check(stackname, context):
    "looks for all of the possible DNS entries for the given route and returns `True` if all are found"
    title('ec2 DNS')
    keys = [
        'ext_node_hostname', # "prod--lax--%s.elifesciences.org"
        'full_hostname', # "prod--lax.elifesciences.org", "prod--journal.elifesciences.org"
        'project_hostname', # "lax.elifesciences.org", "journal.elifesciences.org"
    ]
    domain_map = subdict(context, keys)

    # these don't appear in Route53
    # domain_map['cloudfront'] = (context.get('cloudfront') or {}).get('subdomains', []) # todo
    domain_map['fastly'] = (context.get('fastly') or {}).get('subdomains', [])

    # `project_hostname` is only exactly what it is for prod stacks.
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
        "given a DNS entry, figures out which AWS Hosted Zone it belongs to"
        bits = dns.split('.')
        if len(bits) == 3: # noqa: SIM108, PLR2004
            name = '.'.join(bits[1:]) + '.'
        else:
            name = dns + '.'
        return hosted_zone_map[name]

    record_map = {}

    def get_records(dns):
        """fetches all of the DNS entries for the Hosted Zone the given `dns` entry belongs to.
        results are cached in `record_map` to prevent multiple lookups."""
        zone_id = hosted_zone_id(dns)
        if zone_id in record_map:
            return record_map[zone_id]
        paginator = conn.get_paginator('list_resource_record_sets')
        results = shallow_flatten([page['ResourceRecordSets'] for page in paginator.paginate(HostedZoneId=zone_id)])
        record_map[zone_id] = results
        return results

    def find_records(dns):
        "fetches all of the DNS records for the given `dns` record's Hosted Zone and returns the A or CNAME ones, if any"
        dnsd = dns + '.'
        records = get_records(dns)
        type_list = ['A', 'CNAME']
        return [r for r in records if r['Name'] == dnsd and r['Type'] in type_list]

    def check_record(label, dns):
        "looks for the given `dns` entry and returns a `problem` if one is not found."
        print('* checking %r' % dns)
        records = find_records(dns)
        if not records:
            description = 'record %r (%r) not found in Route53' % (dns, label)
            details = "records found: %s" % (pformat(records),)
            solution = './bldr update_dns:%s' % (stackname,)
            return problem(description, solution, details)
        return None

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

    return results if results else success()

# ---

def format_problem(problem_triple):
    description, solution, details = problem_triple
    if details:
        return "problem:  %s\n   solution: %s\n   details:  %s" % (description, solution, details)
    return "problem:  %s\n   solution: %s" % (description, solution)

def print_problem_list(problem_list):
    title("report")
    formatted_problem_list = ["%s. %s" % (i + 1, format_problem(p)) for i, p in enumerate(problem_list)]
    print("\n\n".join(formatted_problem_list))

@requires_aws_stack
def fix_infrastructure(stackname):
    """like `update_infrastructure`, but guided recommendations.
    infrastructure but correcting any infrastructure drift and
    *hopefully* fixing and problems. Fix is not guaranteed.
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

    # the original problem was that another instance had 'stolen' the DNS records of the journal--prod instance.
    # update_infrastructure failed because nothing looked out of place.
    # so we check the *expected* DNS records against the actual ones.
    check(has_ec2 and _dns_check(stackname, context))

    # todo: buildvars, ec2 nodes are all running, ...

    if problems:
        print_problem_list(problems)
    else:
        print('no problems detected')
