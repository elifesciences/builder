# eLife Continuous Integration server

## Jenkins

Jenkins is a Continuous Integration tool that is used at elife to:

* build Github projects
* trigger building other projects when all tests pass
* periodically execute a task that doesn't naturally live elsewhere

### Jenkins and Github Webhooks

Jenkins has build jobs triggered by Github via the Jenkin's 'github' plugin.

How? A personal access token was created by a user (me, Luke Skibinski) that 
grants a limited set of permissions to whomever uses it to talk to Github.

The Jenkins github plugin uses this token to create post-commit webhooks on the 
repositories specified in the build tasks.

__This user must have *admin* permissions on the repository to create webhooks__.

Anyone in the 'Super Admins' team on Github will do.

## Docker

_UPDATE 2015-11-05_: Docker is no longer used at elife.

Should we decide to re-instate it, it almost certainly should get it's own state
tree instead of trying to integrate it into the existing one.

----

Docker is a means to 'containerize' processes. A Docker container is an empty 
Linux box. Every command run within the box changes it's state. This state 
information can be committed, like changes within a version control system, 
and then pushed to a registry somewhere. The default and most convenient 
registry is their own at hub.docker.com. This changes can also be semi-automated
with their Dockerfile system, which just runs commands one after the after, 
skipping commands it has cached. Introducing new commands or modifying old 
commands will force those commands and all subsequent ones to be re-run.

A Docker container may only run a single process. Once the process has 
completed, that instance of the container is removed and cannot be returned to.

This presents interesting problems.

## docker support within the elife-builder

The elife-builder project has a separate set of state files for Dockerized 
applications at `salt/docker-salt/` that are mounted within the container 
instead of the typical state tree at `salt/salt/`.
The docker-salt state tree has a reduced base installation and fewer supported
base states.

The `elife-ci` project will install and configure the necessary dependencies for
all Dockerized applications, including dependant third party containers.

## Dockerized projects

Just like Vagrant and AWS, a gap exists between the target system and the 
configuration management (Salt) so a bootstrap process is required to kick 
things off. In this case a `Dockerfile` is used to bring the container to a 
ready state with Salt taking over from there.

The `elife-ci` project contains all of the necessary `Dockerfile` files at 
`salt/salt/elife-ci/docker/` and the `salt/salt/elife-ci/init.sls` contains
commands to bring these to a built state ready for Jenkins or the developer to 
instantiate them.

Projects have to be built differently for Docker. Salt has the very useful 
`service` state that manages running processes in a typical environment that 
just doesn't translate to Docker.

Instead, if multiple processes must be running, there is a program called 
"Supervisor" that can handle this readily. All processes that want to be run
with Supervisor must place a config file in the `/etc/supervisor/conf.d/` dir.
Individual processes can be controlled with the `supervisorctl` command.

This constraint means projects must be configured to be ready to go as close as 
possible before the main process starts with dependant services (mysql, 
memcache, etc) running within their own containers and linked to when started.

To keep as much configuration within Salt as possible, I'm doing service 
detection within the state files with large chunks of configuration that are not
run until an instance of the container is run, at which point I call 
`salt-call state.highstate` to complete configuration and then `supervisord` to
run the main process. 

### docker-elife-base

This is the base container all other Dockerized projects should base their own 
Dockerfile on. It contains the base installation and nothing much else.

### docker-elife-drupal

The elife-drupal project is our most complex project in terms of configuration.

It runs it's own Apache webserver but depends on the official third party 
`mysql` container to provide a database server. The command to bring this 
container up, link it to `mysql`, mount the volumes and finish provisioning 
 is part of the Jenkins configuration and can be found at
`salt/salt/elife-ci/docker/elife-drupal/build.sh`.

What this script does is:

* instantiates the semi-provisioned `elife/docker-elife-drupal` container
* links it to the selenium and mysql containers 
* finishes the provisioning of the container by calling salt-call state.highstate within it 
* runs the script `salt/docker-salt/elife-drupal/run-tests.sh`

