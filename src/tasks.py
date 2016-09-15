"""Miscellanious admin tasks.

If you find certain 'types' of tasks accumulating, they might be 
better off in their own module. This module really is for stuff
that has no home."""
import requests
from buildercore import core, project, bootstrap
from fabric.api import sudo, run, local, task
from fabric.contrib.console import confirm
from decorators import echo_output, requires_aws_stack, requires_project, debugtask
from buildercore import bakery
from buildercore.core import stack_conn
import utils
from buildercore.decorators import osissue

@debugtask
@requires_project
@echo_output
def ami_for_project(pname):
    "returns possible AMIs suitable for given project"
    conn = core.connect_aws_with_pname(pname, 'ec2')
    kwargs = {
        # you're better off just going here:
        # https://cloud-images.ubuntu.com/locator/ec2/
        # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeImages.html#query-DescribeImages-filters
        'filters': {
            #'root-device-type': 'ebs',
            #'virtualization_type': 'hvm',
            'architecture': 'x86_64',
            #'name': 'ubuntu/images/*',
            'name': 'ubuntu/images/*/*14.04*201605*',
            'state': 'available',
            'root-device-name': '/dev/sda1',
        },
        'owners': ['099720109477'] # Canonical
    }
    results = conn.get_all_images(**kwargs)

    print results
    
    print len(results),"results"

    return utils.table(results, ['id', 'root_device_type', 'virtualization_type', 'name'])

    # good for figuring out filters 
    #print results[0].__dict__

@task
@requires_aws_stack
def create_ami(stackname):
    pname = core.project_name_from_stackname(stackname)
    msg = "this will create a new AMI for the project %r. Continue?" % pname
    if not confirm(msg, default=False):
        print 'doing nothing'
        return
    amiid = bakery.create_ami(stackname)
    #amiid = "ami-e9ff3682"
    print 'AWS is now creating AMI with id', amiid
    path = pname + '.aws.ami'
    # wait until ami finished creating?
    #core.update_project_file(pname + ".aws.ami", amiid)
    new_project_file = project.update_project_file(path, amiid)
    output_file = project.write_project_file(new_project_file)
    print '\n' * 4
    print 'wrote', output_file
    print 'updated project file with new ami. these changes must be merged and committed manually'
    print '\n' * 4


#
#
#

@requires_aws_stack
def _update_syslog(stackname):
    with stack_conn(stackname):
        cmd = "salt-call state.sls_id syslog-ng-hook base.syslog-ng test=True"
        return sudo(cmd)

#
# LetsEncrypt + ACME client code
# deprecated. this pair are no longer encouraged.
#

def acme_enabled(url):
    "if given url can be hit and it looks like the acme hidden dir exists, return True."
    url = 'http://' + url + "/.well-known/acme-challenge/" # ll: http://lax.elifesciences.org/.well-known/acme-challenge
    try:
        resp = requests.head(url, allow_redirects=False)
        if 'crm.elifesciences' in url:
            return resp.status_code == 404 # apache behaves differently to nginx
        return resp.status_code == 403 # forbidden rather than not found.
    except:
        # couldn't connect for whatever reason
        return False

@task
@requires_aws_stack
@echo_output
@osissue("*very* useful task. improve with documentation.")
def fetch_cert(stackname):
    # NOTE: this was ported from the old builder and won't work with new instances
    # this isn't a problem because new instances shouldn't be using letsencrypt if
    # they can avoid it.
    try:
        # replicates some logic in builder core
        pname = core.project_name_from_stackname(stackname)
        project_data = project.project_data(pname)

        assert project_data.has_key('subdomain'), "project subdomain not found. quitting"

        instance_id = stackname[len(pname + "-"):]
        is_prod = instance_id in ['master', 'production']

        # we still have some instances that are the production/master
        # instances but don't adhere to the naming yet.
        old_prods = [
            'elife-ci-2015-11-04',
            'elife-jira-2015-06-02'
        ]
        if not is_prod and stackname in old_prods:
            is_prod = True

        hostname_data = core.hostname_struct(stackname)
        domain_names = [hostname_data['full_hostname']]
        if is_prod:
            project_hostname = hostname_data['project_hostname']
            if acme_enabled(project_hostname):
                domain_names.append(project_hostname)
            else:
                print '* project hostname (%s) doesnt appear to have letsencrypt enabled, ignore' % project_hostname

        print '\nthese hosts will be targeted:'
        print '* ' + '\n* '.join(domain_names)

        #pillar_data = cfngen.salt_pillar_data(config.PILLAR_DIR)
        #server = {
        #    'staging': pillar_data['sys']['webserver']['acme_staging_server'],
        #    'live': pillar_data['sys']['webserver']['acme_server'],
        #}
        server = {
            'staging': "https://acme-staging.api.letsencrypt.org/directory",
            'live': "https://acme-v01.api.letsencrypt.org/directory",
        }

        certtype = utils._pick("certificate type", ['staging', 'live'])

        cmds = [
            "cd /opt/letsencrypt/",
            "./fetch-ssl-certs.sh -d %s --server %s" % (" -d ".join(domain_names), server[certtype]),
            "sudo service nginx reload",
        ]

        print
        print 'the following commands will be run:'
        print ' * ' + '\n * '.join(cmds)
        print

        if raw_input('enter to continue, ctrl-c to quit') == '':
            with stack_conn(stackname):
                return run(" && ".join(cmds))

    except AssertionError, ex:
        print
        print "* " + str(ex)
        print
        exit(1)

#
#
#

@debugtask
def diff_builder_config():
    "helps keep three"
    file_sets = [
        [
            "./builder-private-example/pillar/elife.sls",
            "./cloned-projects/builder-base-formula/pillar/elife.sls",
            "./builder-private/pillar/elife.sls"
        ],
        [
            "./projects/elife.yaml",
            "./builder-private/projects/elife-private.yaml",
        ]
    ]
    for paths in file_sets:
        local("meld " + " ".join(paths))

@task
@requires_aws_stack
def repair_cfn_info(stackname):
    with stack_conn(stackname):
        bootstrap.write_environment_info(stackname, overwrite=True)
