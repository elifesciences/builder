from buildercore import core
import utils
from decorators import requires_aws_stack, debugtask, echo_output
import logging
LOG = logging.getLogger(__name__)

@debugtask
@requires_aws_stack
def rds_snapshots(stackname):
    "prints all snapshots for given stack, order by creation time"
    inst = core.find_rds_instances(stackname)[0]
    conn = core.boto_conn(stackname, 'rds', client=True)
    snapshots = conn.describe_db_snapshots(**{
        'DBInstanceIdentifier': inst['DBInstanceIdentifier'],
    })['DBSnapshots']
    data = [(ss['DBSnapshotIdentifier'], ss['SnapshotType'], ss['SnapshotCreateTime']) for ss in snapshots]
    data = sorted(data, key=lambda triple: triple[2])
    for row in data:
        print(row)

@debugtask
@echo_output
def detailed_stack_list(project=None):
    region = utils.find_region()
    results = core.active_aws_stacks(region, formatter=None)
    all_stacks = dict([(i.stack_name, vars(i)) for i in results])
    if project:
        return {k: v for k, v in all_stacks.items() if k.startswith("%s-" % project)}
    return all_stacks
