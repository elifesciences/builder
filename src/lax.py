from fabric.api import run, task, get, local
from decorators import requires_aws_project_stack
from buildercore.core import stack_conn

@task
@requires_aws_project_stack('lax')
def dumpdata(stackname):
    with stack_conn(stackname):
        cmds = [
            'cd /srv/lax/ && ./manage.sh dumpdata --exclude=contenttypes --natural-foreign --natural-primary --indent=4 | gzip -9 - > /tmp/lax-db.json.gz',
        ]
        map(run, cmds)
        get('/tmp/lax-db.json.gz', 'public/lax-db.json.gz')
        local('gunzip public/lax-db.json.gz')

        print '\ndata dumped to `public/lax-db.json`\n'
        return "public/lax-db.json"

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
