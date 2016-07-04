__author__ = 'Luke Skibinski <l.skibinski@elifesciences.org>'
__description__ = """Module that deals with AMI baking!

We bake new AMIs to avoid long deployments and the occasional
runtime bugs that crop up while building brand new machines."""

from buildercore import core, utils
from fabric.contrib.files import exists
from fabric.api import sudo
from .decorators import osissue, osissuefn, testme

@osissue("untested ...")
def prep_stack(stackname):
    "prepare the given stack for an image to be created of it."
    to_be_deleted = [
        '/etc/cfn-info.json',
    ]
    def delete_file(remote_path):
        if exists(remote_path):
            return remote_path, sudo('rm ' + remote_path)
        return remote_path, False

    cmds_to_run = []
    
    with core.stack_conn(stackname):
        map(delete_file, to_be_deleted)
        map(sudo, cmds_to_run)



@testme
def ami_name(stackname):
    # elife-api.2015-12-31
    return "%s.%s" % (core.project_name_from_stackname(stackname), utils.ymd())
        
@core.requires_active_stack
def create_ami(stackname):
    "creates an AMI from the running stack"
    prep_stack(stackname)
    ec2 = core.find_ec2_instance(stackname)[0]
    kwargs = {
        'instance_id': ec2.id,
        'name': core.ami_name(stackname),
        'no_reboot': True,
        #'dry_run': True
    }
    conn = core.connect_aws_with_stack(stackname, 'ec2')
    ami_id = conn.create_image(**kwargs)

    # image.__dict__ == {'root_device_type': u'ebs', 'ramdisk_id': None, 'id': u'ami-6bc99d0e', 'owner_alias': None, 'billing_products': [], 'tags': {}, 'platform': None, 'state': u'pending', 'location': u'512686554592/elife-lax.2015-10-15', 'type': u'machine', 'virtualization_type': u'hvm', 'sriov_net_support': u'simple', 'architecture': u'x86_64', 'description': None, 'block_device_mapping': {}, 'kernel_id': None, 'owner_id': u'512686554592', 'is_public': False, 'instance_lifecycle': None, 'creationDate': u'2015-10-15T16:07:21.000Z', 'name': u'elife-lax.2015-10-15', 'hypervisor': u'xen', 'region': RegionInfo:us-east-1, 'item': u'\n        ', 'connection': EC2Connection:ec2.us-east-1.amazonaws.com, 'root_device_name': None, 'ownerId': u'512686554592', 'product_codes': []}
    def is_pending():
        image = conn.get_all_images(image_ids=[ami_id])[0]
        return image.state == 'pending'
    utils.call_while(is_pending, update_msg="Waiting for AWS to bake AMI %s ... " % ami_id)
    return str(ami_id) # this should be used to update the stack templates

def find_ami(projectname=None):
    "finds the AMI for the given project"
    kwargs = {
        'owners': ['self'], # otherwise you get *all* (public) images on AWS
        'filters': {},
    }
    if projectname:
        kwargs['filters']['name'] = '%s.*' % projectname

    conn = core.connect_aws_with_pname(projectname, 'ec2')
    results = conn.get_all_images(**kwargs)
    
    # when filtered by project, most recent ami is the last item
    return sorted(results, key=lambda image: image.name)

@osissue("only packer.py is using this. might be better off in there.")
def basebox():
    "returns most recent basebox ami"
    return utils.last(find_ami("basebox"))

@testme
@osissue("nothing appears to be using this function")
def project_ami(projectname, base_ami_override=None):
    """returns most recent project ami OR
    the base ami override if one has been specified OR
    the most recent basebox ami, otherwise None if none
    of those things can be found.

    This lets us say "if the elife-website project has
    it's own ami, use that, otherwise, use this Ubuntu 12.04
    ami override."

    or "if the elife-api doesn't have it's own project ami and
    has no other special requirements, use the basebox ami for Ubuntu 14.04"""
    # pylint: disable=no-member
    base_ami_override = type('_', (object,), {'id': base_ami_override})()
    obj = utils.last(find_ami(projectname)) or base_ami_override.id or basebox()
    return obj.id if hasattr(obj, 'id') else obj

def update_ami():
    "we don't update AMIs! we create new ones from a running stack and then delete old ones"
    pass

def destroy_ami():
    "finds any old AMI images and deletes them."
    pass
