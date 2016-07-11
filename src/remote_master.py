"""
builder is installed on the remote master to keep things configured.

this module contains tasks that help maintain configuration"""
from fabric.api import task, local, cd, settings, run, sudo, put, get, abort

@task
def install_update_all_projects():
    print "echo install/update all hit"
