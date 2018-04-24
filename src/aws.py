from buildercore import core
import utils
from decorators import requires_aws_stack, debugtask, echo_output
import logging
LOG = logging.getLogger(__name__)

@debugtask
@requires_aws_stack
@echo_output
def rds_snapshots(stackname):
    from boto import rds
    conn = rds.RDSConnection()
    instance = conn.get_all_dbinstances(instance_id=stackname)[0]
    # all snapshots order by creation time
    objdata = conn.get_all_dbsnapshots(instance_id=instance.id)
    data = sorted(map(lambda ss: ss.__dict__, objdata), key=lambda i: i['snapshot_create_time'])
    return data

@debugtask
@echo_output
def detailed_stack_list(project=None):
    region = utils.find_region()
    results = core.active_aws_stacks(region, formatter=None)
    all_stacks = dict([(i.stack_name, vars(i)) for i in results])
    if project:
        return {k: v for k, v in all_stacks.items() if k.startswith("%s-" % project)}
    return all_stacks
