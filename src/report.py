import dateutil.parser
from functools import partial
from datetime import datetime, timedelta
import os
import utils
from buildercore import core, project, utils as core_utils
from buildercore.utils import lookup, ensure
from functools import wraps
from decorators import format_output

def print_list(row_list, checkboxes=True):
    "given a list of things, prints a markdown list to `stdout` with optional checkboxes."
    template = "- %s"
    if checkboxes:
        template = "- [ ] %s"
    for row in row_list:
        print(template % row)

def print_data(data, output_format):
    output_format_map = {
        'json': partial(core_utils.json_dumps, dangerous=True, indent=4),
        'yaml': core_utils.yaml_dumps,
    }
    core_utils.ensure(output_format in output_format_map, "unsupported output format %r" % output_format)
    print(output_format_map[output_format](data))

def sort_by_env(name):
    """comparator. used when sorting a list of ec2 or cloudformation names.
    basic alphabetical ordering if given `name` cannot be parsed."""
    adhoc = 0 # adhoc/unrecognised names first
    order = {
        'continuumtest': 1,
        'staging': 1,
        'ci': 2,
        'end2end': 3,
        'prod': 4, # prod last
    }
    try:
        pname, env, node = core.parse_stackname(name, all_bits=True)
        # groups results by project name, then a consistent ordering by env, then node
        return "%s%s%s" % (pname, order.get(env, adhoc), node)

    except (ValueError, AssertionError):
        # thrown by `parse_stackname` when given value isn't a string or
        # delimiter not found in string.
        # by returning the given `name` here we get a basic alphabetical order
        # for lists that don't contain an environment.

        # last ditch effort for things like RDS instance names.
        for env in order:
            pos = name.find("-" + env)
            if pos > -1:
                env = name[pos + 1:] # "elife-libero-reviewer-prod" => "prod"
                rest = name[:pos] # "elife-libero-reviewer-prod" => "elife-libero-reviewer"
                key = "%s%s" % (rest, order.get(env, adhoc)) # "elife-libero-reviewer4"
                return key

        return name

def print_report(results, as_list=True, checkboxes=True, ordered=True, output_format='json', *args, **kwargs):
    ordered = utils.strtobool(ordered)
    checkboxes = utils.strtobool(checkboxes)
    as_list = utils.strtobool(as_list)
    if not results:
        return
    # only sort the results if we have a non-empty list of strings
    if isinstance(results, list) and results and isinstance(results[0], str) and ordered:
        results = sorted(results, key=sort_by_env)
    if as_list:
        print_list(results, checkboxes)
    else:
        print_data(results, output_format)

def report(task_fn):
    "wraps a task, printing it's results as a sorted list to `stdout`."
    @wraps(task_fn)
    def _wrapped(as_list=True, checkboxes=True, ordered=True, *args, **kwargs):
        results = task_fn(*args, **kwargs)
        print_report(results, as_list, checkboxes, ordered, *args, **kwargs)
        return results
    return _wrapped

def configured_report(**kwargs):
    "just like `report`, but you can pre-configure output options"
    def _wrap1(task_fn):
        @wraps(task_fn)
        def _wrap2(*report_args, **report_kwargs):
            formatting_params = ['as_list', 'checkboxes', 'ordered', 'output_format']
            formatting_kwargs = {key: report_kwargs.pop(key) for key in formatting_params if key in report_kwargs}
            results = task_fn(*report_args, **report_kwargs)
            kwargs.update(formatting_kwargs)
            print_report(results, **kwargs)
            return results
        return _wrap2
    return _wrap1

# ---

@report
def all_projects():
    "All project names"
    return project.project_list()

@report
def all_formulas():
    "All known Salt formulas."
    # `project` will give us a map of `project-name: formula-list`
    formula_list = project.project_formulas().values()
    # flatten the list of lists into a single unique list
    formula_list = set(core_utils.shallow_flatten(formula_list))
    # remove any empty values, probably from reading the `defaults` section
    formula_list = filter(None, formula_list)
    # extract just the name from the formula url
    formula_list = map(os.path.basename, formula_list)
    return formula_list

@report
def all_ec2_projects():
    """All project names using ec2.
    Excludes alt-configs defined in the 'defaults' section."""
    alt_black_list = ['fresh', 'snsalt', 's1804', '1804', '2004', 's2004', 'standalone']

    def has_ec2(pname, pdata):
        if lookup(pdata, 'aws.ec2', None):
            return pname
        # if evidence of an ec2 section not found directly, check alternate configurations
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            if alt_name in alt_black_list:
                continue
            # we wrap in 'aws' here because we're looking for 'aws.ec2', not the un-nested 'ec2'
            if has_ec2(pname, {'aws': alt_data}):
                return pname
    results = [has_ec2(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results

def _all_ec2_instances(state):
    return [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]

@report
def all_ec2_instances(state=None):
    """All ec2 instance names.
    Set `state` to `running` to see all running ec2 instances."""
    return _all_ec2_instances(state)

def process_project_security_updates():
    "Project and environment data for the selfsame Jenkins job."
    results = sorted(_all_ec2_instances(state=None), key=sort_by_env)
    project_blacklist = [
        'basebox',
        'containers',
    ]
    env_blacklist = [
        'prod'
    ]
    stack = [] # [(stackname, [env1,env2,env3]), ...]
    for stackname in results:
        try:
            pname, iid, nid = core.parse_stackname(stackname, all_bits=True)
            if pname in project_blacklist:
                print('skipping %s: project %r in blacklist' % (stackname, pname))
                continue

            if iid in env_blacklist:
                print('skipping %s: env %r in blacklist' % (stackname, iid))
                continue

            # add project to stack because stack is empty, or because the project has changed.
            if not stack or stack[-1][0] != pname:
                stack.append((pname, []))

            # add env to project's list of envs if list of envs is empty or,
            # the last env seen is different to this one.
            if not stack[-1][1] or stack[-1][1][-1] != iid:
                stack[-1][1].append(iid)

        except Exception as exc:
            print('skipping %s: unhandled exception %r' % (stackname, exc))
            continue

    print("project_envlist = [")
    for pname, envlist in stack:
        print('    ["%s", "%s"],' % (pname, ",".join(envlist)))
    print("]")

@report
def all_ec2_instances_for_salt_upgrade():
    "All ec2 instance names suitable for a Salt upgrade"
    ignore_these = [
        "basebox--2004--1", # ami creation, periodically destroyed and recreated
        "master-server--prod--1", # updated in separate step
        # created and destroyed by jenkins.
        # the template is 'containers--jenkins-plugin-ami'
        "containers-jenkins-plugin",
        "kubernetes-aws--flux-prod",
        "kubernetes-aws--flux-test",
        "kubernetes-aws--test",
    ]
    return [i for i in _all_ec2_instances(state=None) if i not in ignore_these]

@report
def all_adhoc_ec2_instances(state='running'):
    "All ec2 names in an unknown environment."

    # extract a list of environment names from the project data
    def known_environments(pdata):
        "returns the names of all alt-config names for given project data"
        return list(pdata.get('aws-alt', {}).keys())
    env_list = core_utils.shallow_flatten(map(known_environments, project.project_map().values()))

    # append known good environments and ensure there are no dupes
    fixed_env_list = ['prod', 'end2end', 'continuumtest', 'ci', 'preview', 'continuumtestpreview']
    env_list += fixed_env_list
    env_list = list(set(filter(None, env_list)))

    # extract the names of ec2 instances that are not part of any known environment
    def adhoc_instance(ec2_name):
        "predicate, returns True if stackname is *not* in a known environment"
        stackname = ec2_name # not always true, but close enough
        try:
            iid = core.parse_stackname(stackname, all_bits=True, idx=True)['instance_id']
            return iid not in env_list
        except (ValueError, AssertionError):
            # thrown by `parse_stackname` when given value isn't a string or
            # delimiter not found in string.
            return True
    instance_list = [ec2['TagsDict']['Name'] for ec2 in core.ec2_instance_list(state=state)]
    return filter(adhoc_instance, instance_list)

def all_projects_using(key):
    "List all projects using RDS."

    def has_(pname, pdata):
        if lookup(pdata, key, None):
            return pname
        # if evidence of a 'foo' section not found directly, check alternate configurations
        for alt_name, alt_data in pdata.get('aws-alt', {}).items():
            # we wrap in 'aws' here because we're looking for 'aws.foo', not the un-nested 'foo'
            if has_(pname, {'aws': alt_data}):
                return pname
    results = [has_(pname, pdata) for pname, pdata in project.project_map().items()]
    results = filter(None, results)
    return results

@report
def all_rds_projects():
    return all_projects_using('aws.rds')

@report
def all_lb_projects():
    return list(all_projects_using('aws.elb')) + list(all_projects_using('aws.alb'))

@report
def all_cloudfront_projects():
    return all_projects_using('aws.cloudfront')

@report
def all_rds_instances(**kwargs):
    """All RDS instances.
    Results ordered by environment, where possible."""
    return [i['DBInstanceIdentifier'] for i in core.find_all_rds_instances()]

@configured_report(as_list=False)
def long_running_large_ec2_instances(**kwargs):
    """All large, unknown, long-running ec2 instances.
    'large' means > t3.medium.
    'unknown' means non-t3 or non-ci/non-end2end/etc.
    'long time' is 4hrs."""
    #open('/tmp/output.json', 'w').write(core_utils.json_dumps(core.ec2_instance_list(state='running'), dangerous=True))
    #result_list = json.load(open('/tmp/output.json', 'r'))
    result_list = core.ec2_instance_list(state='running')

    known_instance_types = {
        't3.nano': 0,
        't3.micro': 1,
        't3.small': 2,
        't3.medium': 3,
        't3.large': 4,
        't3.xlarge': 5,
        't3.2xlarge': 6
    }

    large_inst = 't3.large'

    known_env_list = [
        'ci', 'end2end', 'continuumtest', 'prod',
        'flux-test', 'flux-prod'
    ]

    long_running_duration = 4 # hrs

    # large or unknown
    def is_large_instance(result):
        inst_type = result['InstanceType']
        if inst_type not in known_instance_types:
            return result
        if known_instance_types[inst_type] >= known_instance_types[large_inst]:
            return result

    def is_long_running(result):
        launch_time = result['LaunchTime']
        if isinstance(launch_time, str):
            launch_time = datetime.fromisoformat(launch_time)
        now = core_utils.utcnow()
        return (now - launch_time) > timedelta(hours=long_running_duration)

    def known_env(result):
        return lookup(result, 'TagsDict.Environment', None) in known_env_list

    def comp(result):
        return is_large_instance(result) and is_long_running(result) and not known_env(result)

    large_instances = list(filter(comp, result_list))

    def result_item(result):
        key_list = ['TagsDict.Name', 'LaunchTime', 'InstanceId', 'InstanceType', 'State.Name']
        return {key: lookup(result, key, None) for key in key_list}

    return list(map(result_item, large_instances))

@configured_report(as_list=False)
def all_amis_to_prune():
    """All AMIs that are old and in the 'available' state.
    Results are ordered oldest to newest.
    Output is fed into a `tasks.py` task to prune old AMIs."""

    conn = core.boto_client('ec2', core.find_region())
    image_list = conn.describe_images(Owners=['self'])

    old_months = 3
    old_months = timedelta(days=(28 * old_months))
    now = core_utils.utcnow()

    def is_known(image):
        return \
            image['Name'].startswith('basebox-') or \
            image['Name'].startswith('containers-')

    def is_old(image):
        image_created = dateutil.parser.parse(image['CreationDate'])
        return (now - image_created) > old_months

    def is_available(image):
        return image['State'] == "available"

    def comp(image):
        return is_known(image) and is_old(image) and is_available(image)
    results = list(filter(comp, image_list['Images']))

    # prune the Image data down to something more readable
    interesting_keys = ['Name', 'CreationDate', 'ImageId']
    results = [{key: lookup(image, key) for key in interesting_keys} for image in results]

    # sort by date asc (oldest to newest)
    results = sorted(results, key=lambda image: image['CreationDate'])

    return results

@format_output('python')
def ec2_node_count(stackname):
    "ec2 node count for given `stackname`."
    return len(core.ec2_data(stackname, state='pending|running|stopping|stopped'))

# TODO: this report isn't precious or being used, it should probably filter the
# list of stacks to anything that isn't deleted or in the process of being deleted.
# the logic in buildercore/core.py doesn't exist for it though.
@report
def all_cloudformation_instances():
    "All (steady) Cloudformation stacks."
    return [stack[0] for stack in core.steady_aws_stacks(core.find_region())]

def _ri_recommendations_ec2():
    "returns a Reserved Instance purchase recommendation for EC2 instances"
    lu = {
        't3.nano': 1,
        't3.micro': 2,
        't3.small': 4,
        't3.medium': 8,
        't3.large': 16,
        't3.xlarge': 32,
        't3.2xlarge': 64
    }
    raw_data = core.ec2_instance_list(state=None)
    row_list = []
    for ec2 in raw_data:
        inst = ec2['InstanceType'] # "t3.large"
        if inst not in lu:
            # only consider the t3 family
            continue
        row_list.append({
            'Name': ec2['TagsDict'].get('Name'),
            'InstanceType': inst,
            'Env': ec2['TagsDict'].get('Environment'), # "prod", "staging", "continuumtest", etc
            'ComputeUnits': lu[inst]
        })

    # only consider instances in environments that are always on.
    # ci, end2end and adhoc instances are excluded.
    always_on_envs = [
        'prod',
        'continuumtest',
        'continuumtestpreview',
        'demo',
        'staging',
        'flux-test',
        'flux-prod',
    ]
    included_rows, excluded_rows = core_utils.splitfilter(lambda row: row['Env'] in always_on_envs, row_list)

    result = {
        'summary': {
            'total-ec2-instances': len(raw_data),
            'total-t3-ec2-instances': len(row_list), # good to compare to overal total
            'total-always-on-t3-ec2-instances': len(included_rows),
            #'instance-type-breakdown': core_utils.mkidx(lambda row: row['InstanceType'], row_list),
            #'env-type-breakdown': core_utils.mkidx(lambda row: row['Env'], row_list),

            'total-t3-units': sum([row['ComputeUnits'] for row in row_list]),
            'total-always-on-t3-units': sum(row['ComputeUnits'] for row in included_rows),
        },
        #'rows-included': included_rows,
        #'rows-excluded': excluded_rows,
    }

    # "253 * t3.nano"
    result['recommendations'] = "%s * t3.nano" % result['summary']['total-always-on-t3-units']

    return result

def _ri_recommendations_rds():
    "returns a Reserved Instance purchase recommendation for RDS instances"
    lu = {
        #'db.t3.nano': 1,  # not available for reservation
        'db.t3.micro': 2,  # so use this for multipler
        'db.t3.small': 4,
        'db.t3.medium': 8,
        'db.t3.large': 16,
        'db.t3.xlarge': 32,
        'db.t3.2xlarge': 64
    }
    raw_data = core.find_all_rds_instances()
    row_list = []
    for rds in raw_data:
        inst = rds['DBInstanceClass'] # "db.t3.micro"
        ensure(inst in lu, "instance type not found: %s" % inst)
        row_list.append({
            'Name': rds['DBInstanceIdentifier'],
            'InstanceType': inst,
            'Engine': rds['Engine'], # "postgres"
            'MultiAZ': rds['MultiAZ'], # true/false
            'AZ': rds['AvailabilityZone'], # "us-east-1"
            'Env': rds['TagsDict'].get('Environment'),
            'ComputeUnits': lu[inst] / lu['db.t3.micro']
        })

    # RDS instances are always on because they take too long to turn off
    included_rows, excluded_rows = core_utils.splitfilter(lambda row: True, row_list)

    result = {
        'summary': {
            'total-units': sum(row['ComputeUnits'] for row in included_rows),

            'total-multi-az-instances': len([row for row in included_rows if row['MultiAZ']]),
            'total-postgres-instances': len([row for row in included_rows if row['Engine'] == 'postgres']),
            'total-mysql-instances': len([row for row in included_rows if row['Engine'] == 'mysql']),

            #'az-type-breakdown': core_utils.mkidx(lambda row: row['MultiAZ'], included_rows),
            #'instance-type-breakdown': core_utils.mkidx(lambda row: row['InstanceType'], included_rows),
            #'env-type-breakdown': core_utils.mkidx(lambda row: row['Env'], included_rows),
        },
        #'rows-included': included_rows,
        #'rows-excluded': excluded_rows,
    }

    # reservations are broken down by: engine, multi-az
    recommendations = core_utils.mkidx(lambda row: "%s+%s" % (row['Engine'], 'MultiAZ' if row['MultiAZ'] else 'SingleAZ'), included_rows)

    # we then need to sum the ComputeUnits and times them by db.t3.micro (not db.t3.nano)
    recommendations = {key: "%s * db.t3.micro" % sum([row['ComputeUnits'] for row in val]) for key, val in recommendations.items()}

    result['recommendations'] = recommendations

    return result

@configured_report(as_list=False, output_format='json')
def ri_recommendations():
    return {
        'ec2': _ri_recommendations_ec2(),
        'rds': _ri_recommendations_rds(),
    }
