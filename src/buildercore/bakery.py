__description__ = """Module that deals with AMI baking!

We bake new AMIs to avoid long deployments and the occasional
runtime bugs that crop up while building brand new machines."""

from buildercore import core, utils, bootstrap, config
from buildercore.utils import ensure

def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (core.project_name_from_stackname(stackname), utils.ymd())

@core.requires_active_stack
def create_ami(stackname, name=None):
    "creates an AMI from the running stack"
    # NOTE: alfred is able to run this task as BOOTSTRAP_USER because it created the instance (somehow).
    # or I downloaded the key for it (I don't recall).
    with core.stack_conn(stackname, username=config.BOOTSTRAP_USER):
        bootstrap.clean_stack_for_ami()
    ec2 = core.find_ec2_instances(stackname)[0]
    kwargs = {
        'Name': name or ami_name(stackname),
        'NoReboot': True,
        # 'DryRun': True
    }
    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Instance.create_image
    ami = ec2.create_image(**kwargs)
    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Image
    ami.wait_until_exists(Filters=[{
        'Name': 'state',
        'Values': ['available'],
    }])
    return str(ami.id) # this should be used to update the stack templates

def delete_ami(image_id):
    """'deregisters' an AMI and deletes the EBS snapshot backing it.
    returns a map of the AMI and snapshot data that were deleted."""
    conn = core.boto_client('ec2', core.find_region())
    resp = conn.describe_images(Filters=[{'Name': 'image-id', 'Values': [image_id]}])
    image = resp['Images'][0]

    snapshot_list = [s for s in image['BlockDeviceMappings'] if 'Ebs' in s]
    ensure(snapshot_list, "AMI has no EBS volumes attached: %s" % image_id)
    ensure(len(snapshot_list) == 1, "AMI has multiple EBS volumes attached: %s" % image_id)
    snapshot = snapshot_list[0]

    conn.deregister_image(ImageId=image_id)
    conn.delete_snapshot(SnapshotId=snapshot['Ebs']['SnapshotId'])

    return {'image': image, 'snapshot': snapshot}
