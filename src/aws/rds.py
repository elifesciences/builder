from buildercore import core
from decorators import requires_aws_stack, format_output
import logging
LOG = logging.getLogger(__name__)

# lsh@2022-09-16: this function was created ages ago as 'rds_snapshot_list' and lived in './aws.py'.
# it isn't being used as far as I can tell but it is serving to illustrate where to put general purpose aws tasks.
# candidate for deletion.
@format_output('json')
@requires_aws_stack
def snapshot_list(stackname):
    "Snapshot names and IDs for given stack, ordered by creation time."
    inst = core.find_rds_instances(stackname)[0]
    conn = core.boto_conn(stackname, 'rds', client=True)
    snapshots = conn.describe_db_snapshots(**{
        'DBInstanceIdentifier': inst['DBInstanceIdentifier'],
    })['DBSnapshots']
    data = [(ss['DBSnapshotIdentifier'], ss['SnapshotType'], ss['SnapshotCreateTime']) for ss in snapshots]
    return sorted(data, key=lambda triple: triple[2])
