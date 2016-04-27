from fabric.api import run, task, get, local
from decorators import requires_aws_project_stack
from aws import stack_conn

@task
@requires_aws_project_stack('elife-lax')
def dumpdata(stackname):
    with stack_conn(stackname):
        cmds = [
            'cd /srv/lax/ && ./manage.sh dumpdata | gzip -9 - > /tmp/lax-db.json.gz',
        ]
        map(run, cmds)
        get('/tmp/lax-db.json.gz', 'public/lax-db.json.gz')
        local('gunzip public/lax-db.json.gz')
        print '\ndata dumped to `public/lax-db.json`\n'
