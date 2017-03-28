from fabric.api import run, task, get
from fabric.context_managers import cd
from decorators import requires_aws_project_stack
from buildercore.core import stack_conn, utils as core_utils


# TODO: replace this download db thing with calls to UBR

@task(alias='dumpdata')
@requires_aws_project_stack('lax')
def download_db_fixtures(stackname):
    """downloads a dump of the lax database as *django fixtures* to the
    current directory as 'stackname-yyyymmddhhmmss'.json.gz"""

    dtstamp = core_utils.utcnow().isoformat().rsplit('.', 1)[0].replace(':', '-')
    local_path = "./%s.%s.json.gz" % (stackname, dtstamp)
    remote_path = '/tmp/db.json.gz'

    with stack_conn(stackname), cd('/srv/lax/'):
        # dump fixtures
        run('./manage.sh dumpdata --exclude=contenttypes --natural-foreign --natural-primary --indent=4 | '
            'gzip -9 - > ' + remote_path)

        # download
        get(remote_path, local_path)

        # remove remote dump
        run('rm ' + remote_path)

        print '\ndata dumped to `%s`\n' % local_path
        return local_path


'''
@task
def loaddata():
    from_stack = None
    to_stack = None

    backup = dumpdata(to_stack)
    rename(backup)

    dump = dumpdata(from_stack) # prompts to dump from
    upload(dump, to_stack)
    with stack_conn(to_stack):
        cmd = 'cd /srv/lax/ && ./manage.sh flush --noinput && ./manage.sh loaddata /tmp/lax-db.json'
        run(cmd)
'''
