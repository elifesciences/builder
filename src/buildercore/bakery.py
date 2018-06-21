__description__ = """Module that deals with AMI baking!

We bake new AMIs to avoid long deployments and the occasional
runtime bugs that crop up while building brand new machines."""

from buildercore import core, utils, bootstrap, config

def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (core.project_name_from_stackname(stackname), utils.ymd())

@core.requires_active_stack
def create_ami(stackname, name=None):
    "creates an AMI from the running stack"
    with core.stack_conn(stackname, username=config.BOOTSTRAP_USER):
        bootstrap.clean_stack_for_ami()
    ec2 = core.find_ec2_instances(stackname)[0]
    kwargs = {
        'Name': ami_name(stackname) if name is None else name,
        'NoReboot': True,
        #'DryRun': True
    }
    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Instance.create_image
    ami = ec2.create_image(**kwargs)
    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Image
    ami.wait_until_exists(Filters=[{
        'Name': 'state',
        'Values': ['available'],
    }])
    return str(ami.id) # this should be used to update the stack templates
