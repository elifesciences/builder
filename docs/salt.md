# SaltStack

The `builder` project uses [SaltStack](https://github.com/saltstack/salt) to provision Vagrant virtual machines and AWS EC2 instances.

The process for installing Salt and configuring it differs slightly depending on the platform. Vagrant instances use a masterless strategy and AWS instances use a master+minion strategy, however after the platform has been 'bootstrapped' the same instructions are used on both.

## Installing Salt

A project called [salt-bootstrap](https://github.com/saltstack/salt-bootstrap) is used to install Salt on both Vagrant and AWS EC2 minions. The builder script that does this is found here: `./scripts/bootstrap.sh`.

For AWS EC2, the builder commands `update` and `update_infrastructure` will upload and execute this script. 
If Salt is not detected then `bootstrap.sh` will call the `salt-bootstrap` script with the correct parameters. If an older version of Salt is detected, then only calls using `update_infrasture` (not `update`) will upgrade the version of Salt.

For Vagrant, the `vagrant up` and `vagrant provision` commands will run this script.

## Upgrading Salt

Salt works best when both the master and clients are running on the same version of Salt, however there is backwards support for older clients talking to newer masters.

The version of Salt used is found in the `defaults.salt` section of [the project file](https://github.com/elifesciences/builder/blob/master/projects/elife.yaml). When an EC2 instance is created the version of Salt to install is included in the list of build-time data, called it's `context`. It's this value that is passed to the `bootstrap.sh` script that determines whether Salt needs upgrading or not.

Salt has been very stable with almost no problems upgrading `builder` instances from `2014.7` to `2015.8` to `2016.3` to `2017.8`.

Detailed instructions for upgrading Salt are in the separate document ['Upgrading Salt'](upgrading-salt.md)

## Grains

[Grains](https://docs.saltstack.com/en/latest/topics/grains/) are provided on EC2 instances and can be useful to target particular servers. Besides standard grains like `osrelease` (`16.04`) and `oscodename` (`xenial`), the following custom grains are set up during bootstrap:

- `project` e.g. `elife-xpub`

And can be [accessed](https://docs.saltstack.com/en/latest/ref/modules/all/salt.modules.grains.html#salt.modules.grains.get) like any other grain. 

From `.sls` and jinja template files:

    {% salt['grains.get']('project') %}
    
From the command line on the `master-server`:

    # salt "elife-xpub*" grains.get project
    
From a minion:
    
    # salt-call grains.get project
