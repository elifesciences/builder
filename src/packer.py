import copy
from os.path import join
from fabfile import PROJECT_DIR
from fabric.api import task, local, settings
import utils
from utils import walk_nested_struct
from decorators import requires_project, echo_output, debugtask
from buildercore import config, utils as core_utils, project
import os, json
from datetime import datetime
from buildercore.decorators import osissue

TEMPLATE = {
    "builders": [
        # disabled. too fragile, time waster
        #{"type": "amazon-ebs",
        # "region": lambda p: prj(p, 'aws.region'),
        # #"source_ami": lambda p: prj(p, 'aws.ec2.ami'),
        # "source_ami": "ami-9eaa1cf6",
        # "instance_type": lambda p: prj(p, 'aws.type'),
        # "ssh_username": "ubuntu",
        # "ami_name": 'test-ami-{{ timestamp }}',
        # "vpc_id": lambda p: prj(p, 'aws.vpc-id'),
        # "subnet_id": lambda p: prj(p, 'aws.subnet-id'),
        #},
        {"type": "virtualbox-ovf",
         "source_path": lambda p: vagrant_path(prj(p, 'vagrant.box')),
         "ssh_username": "vagrant",
         "ssh_password": "vagrant",
         "shutdown_command": "echo 'vagrant' | sudo -S shutdown -P now",
         #"output_directory": "packer",
         "headless": True,
         "vboxmanage": [
             ["modifyvm", "{{.Name}}", "--memory", "2048"],
             ["modifyvm", "{{.Name}}", "--cpus", "2"],
             ["sharedfolder", "add", "{{.Name}}", "--name", "vagrant", "--hostpath", PROJECT_DIR, "--readonly"],
             ["sharedfolder", "add", "{{.Name}}", "--name", "salt-state", "--hostpath", join(PROJECT_DIR, "salt/salt/"), "--readonly"],
             ["sharedfolder", "add", "{{.Name}}", "--name", "salt-pillar", "--hostpath", join(PROJECT_DIR, "salt/pillar/"), "--readonly"],
             ["sharedfolder", "add", "{{.Name}}", "--name", "salt-dev-pillar", "--hostpath", join(PROJECT_DIR, "salt/dev-pillar/"), "--readonly"],             
             ]
        }
    ],
    "provisioners": [
        # disabled in favour of shared bootstrap script
        #{"type": "salt-masterless",
        # "local_state_tree": join(PROJECT_DIR, "salt/salt"),
        # "local_pillar_roots": join(PROJECT_DIR, "salt/pillar"),
        # "remote_state_tree": "/srv/salt/",
        # "remote_pillar_roots": "/srv/pillar/",
        # "minion_config": lambda p: join(PROJECT_DIR, "packer/%s-packer.minion" % p),
        # "skip_bootstrap": True # base box should already be configured with salt
        #},
        {"type": "shell",
         "scripts": [
             join(PROJECT_DIR, "scripts/mount-shared-folders.sh"),
             join(PROJECT_DIR, "scripts/set-hostname.sh"), # hostname is used as the minion ID
             join(PROJECT_DIR, "scripts/bootstrap.sh"),
             join(PROJECT_DIR, "scripts/init-minion.sh"),
             join(PROJECT_DIR, "scripts/packer-cleanup.sh")],
         "environment_vars": lambda p: [
             "SALT_VERSION=%s" % prj(p, 'salt'),
             "PROJECT=%s-dev" % p],
        }
    ],
    "post-processors": [
        {"type": "vagrant",
         "compression_level": 9,
         "output": lambda p: template_path(p, "vagrant.box")}
    ],
}

def template_path(pname, suffix):
    # ll: .../packer/basebox.json
    #     .../packer/basebox-meta.json
    #     .../packer/basebox-vagrant.box
    if not suffix.startswith('.'):
        suffix = "-"+suffix
    return join(PROJECT_DIR, 'packer', pname + suffix)

def vagrant_path(boxname):
    boxname = boxname.replace('/', '-VAGRANTSLASH-')
    subpath = os.path.expanduser(join("~/.vagrant.d", 'boxes', boxname))
    subdirs = filter(os.path.isdir, map(lambda p: join(subpath, p), os.listdir(subpath)))
    latest = os.path.basename(max(subdirs, key=os.path.getmtime))
    path = join(subpath, latest, 'virtualbox', 'box.ovf')
    assert os.path.exists(path), "couldn't find path: %s" % path
    return os.path.abspath(os.path.expanduser(path))

def box_metadata_url(pname):
    metaname = os.path.basename(template_path(pname, "meta.json"))
    return join(config.PACKER_BOX_S3_PATH, metaname)

def box_url(pname):
    pname = prj(pname, 'vagrant.box').split('/')[-1]
    boxname = os.path.basename(template_path(pname, "vagrant.box"))
    return join(config.PACKER_BOX_S3_PATH, boxname)

def box_name(pname):
    return join(config.PACKER_BOX_PREFIX, pname) # ll: elifesciences/basebox

def prj(pname, path):
    return core_utils.lookup(project.project_data(pname), path)



#
#
#

#def minion_config(pname):
#    x = "file_client: local\nid: %s-packer" % pname
#    fname = 'packer/%s-packer.minion' % pname
#    open(fname, 'w').write(x)
#    print 'wrote',fname

def render_template(pname):
    "walk the TEMPLATE and call any callables"
    template = copy.deepcopy(TEMPLATE)
    def fn(x):
        if callable(x):
            return x(pname)
        return x    
    return walk_nested_struct(template, fn)

def render(pname):
    "renders the packer template and writes it's json to something like elife-builder/packer/pname.json"
    assert utils.mkdirp('packer'), "failed to create the 'packer' dir"
    out = json.dumps(render_template(pname), indent=4)
    fname = template_path(pname, '.json')
    open(fname, 'w').write(out)
    print out
    print 'wrote',fname
    return fname

def validate(pname):
    fname = template_path(pname, '.json')
    ret = os.system('packer-io validate %s' % fname)
    assert ret == 0, "failed to validate template %s" % fname
    return fname

def sha256sum(pname):
    ret = local("sha256sum %s" % template_path(pname, "vagrant.box"), capture=True)
    assert ret.return_code == 0, "failed to generate sha256 sum"
    return ret.split(" ")[0]

#
# 
#

@debugtask
@requires_project
def generate_meta(pname):
    """a .box file has metadata associated with it. this returns the necessary struct.
    see `write_meta` to take this output and write the json to the project's
    `meta.json` file, updating any existing meta it finds."""
    vagrant_name = os.path.basename(template_path(pname, "vagrant.box"))
    meta = {
        "name": box_name(pname),
        "description": "This box contains company secrets.",
        "versions": [{
            "version": datetime.now().strftime("%Y.%m.%d"),
            "providers": [{
                "name": "virtualbox",
                "url": join(config.PACKER_BOX_S3_HTTP_PATH, vagrant_name),
                "checksum_type": "sha256",
                "checksum": sha256sum(pname),
                }]
            }]
        }
    fname = template_path(pname, 'meta.json')
    if os.path.exists(fname):
        old_meta = json.load(open(fname, 'r'))
        # remove any old meta that has the same version as the new meta
        nv = meta['versions'][0]
        old_versions = [ov for ov in old_meta['versions'] if ov['version'] != nv['version']]
        meta['versions'].extend(old_versions)
    json.dump(meta, open(fname, 'w'), indent=4)
    print 'wrote',fname

@debugtask
@requires_project
def generate_template(pname):
    render(pname)
    validate(pname)

@debugtask
@requires_project
def upload_box(pname):
    "uploads the box and it's metadata to S3"
    box = template_path(pname, "vagrant.box")
    cmd = "aws s3 cp %s %s" % (box, config.PACKER_BOX_S3_PATH)
    print 'uploading box ...'
    print cmd
    assert os.system(cmd) == 0, "failed to upload box to s3"

    meta = template_path(pname, "meta.json")
    cmd = "aws s3 cp %s %s --content-encoding application/json" % (meta, config.PACKER_BOX_S3_PATH)
    print 'uploading meta ...'
    print cmd
    assert os.system(cmd) == 0, "failed to upload meta to s3"

@debugtask
@requires_project
def add_box(pname):
    "to build an image of a project we need it's box on the system, otherwise it dies :("
    box = prj(pname, 'vagrant.box')
    url = prj(pname, 'vagrant.box-url')
    target = url if url else box
    cmd = "vagrant box add %s" % target # give vagrant the box url if we have one
    ret = os.system(cmd)
    # something fishy here... disabling assertion
    # if box exists will return '1'
    # I have seen it return 256 however
    #assert ret not in [0, 1], "vagrant failed to find or download the given box! exit code %s" % ret
    return ret

@task
@requires_project
def remove_box(pname):
    boxname = prj(pname, 'vagrant.box')
    cmd = 'vagrant box remove %s' % boxname
    os.system(cmd)

@debugtask
@requires_project
def update_project_file(pname):
    "detects if a box exists for project, updates project file"
    updates = [
        ('%s.vagrant.box' % pname, box_name(pname)),
        ('%s.vagrant.box-url' % pname, box_metadata_url(pname))
    ]
    if pname == 'basebox':
        # special handling when updating the basebox
        # leave the actual basebox project's box and box_url settings as-is
        updates = [
            ('defaults.vagrant.box', box_name(pname)),
            ('defaults.vagrant.box-url', box_metadata_url(pname))
        ]

    project_file = 'asdf'
            
    project_data = core_utils.ordered_load(open(project_file, 'r'))
    for path, new_val in updates:
        project_data = project.update_project_file(path, new_val, project_data)
    project.write_project_file(project_data)
    print 'wrote',project_file
    return project_data

@task
def add_all_boxes():
    #_, projects = core.all_projects()
    projects = project.project_list()
    # kinda gross because everything is keyed to the project, but works nicely
    boxes = {prj(pname, 'vagrant.box'): pname for pname in projects.keys()}
    return map(add_box, boxes.values())


#
#
#

@task
@requires_project
def build(pname):
    "build a vagrant .box for the given project, upload it, update the projects/elife.yaml file"
    generate_template(pname)
    add_box(pname)
    cmd = "packer-io build %s" % template_path(pname, ".json")
    ret = os.system(cmd)
    assert ret == 0, "packer-io failed to complete successfully"
    expected_box = template_path(pname, "vagrant.box")
    assert os.path.exists(expected_box), "the '.box' file we were expecting doesn't exist: %r" % expected_box
    generate_meta(pname)
    upload_box(pname)
    update_project_file(pname)

@task
@requires_project
def download_box(pname):
    "just download the vagrant .box for given project"
    boxurl = box_url(pname)
    if not boxurl.startswith('s3://'):
        print 'this task only downloads from s3. unhandled url',boxurl
        exit(1)
    dest = join('/tmp', os.path.basename(boxurl))
    if os.path.exists(dest):
        print 'file %s already exists, skipping download. move or rename the file to re-download' % dest
        return dest
    cmd = "aws s3 cp %s %s" % (boxurl, dest)
    assert local(cmd).return_code == 0, "failed to successfully download %s" % boxurl
    return dest

@debugtask
@echo_output
@requires_project
def box_installed(pname):
    "returns True if the basebox for the given project is downloaded and installed"
    with settings(warn_only=True):
        boxname = prj(pname, 'vagrant.box')
        cmd = "vagrant box list | grep %s" % boxname
        return local(cmd).return_code == 0

@task
@requires_project
def install_box(pname):
    """alternative to 'vagrant add boxname'.
    downloads and installs a vagrant box.
    macs appear to have a problem maintaining a connection to S3,
    so this task downloads it for Vagrant and then adds it from the filesystem"""
    if box_installed(pname):
        print 'the .box file for %r has already been installed (%s)' % (pname, prj(pname, 'vagrant.box'))
        return
    dest = download_box(pname)
    with settings(warn_only=True):
        cmd = "vagrant box add %s %s" % (prj(pname, 'vagrant.box'), dest)
        retval = local(cmd).return_code
        if retval == 0 and os.path.exists(dest):
            print 'removing downloaded file ...'
            local('rm -i %s' % dest)

@task
@osissue("this and a few other functions in packer.py really need to purged. they don't work as expected")
def install_basebox():
    # any box that uses the elife basebox
    return install_box('elife-api')
