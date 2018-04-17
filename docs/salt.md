# SaltStack

The `builder` project uses [SaltStack](https://github.com/saltstack/salt) to provision Vagrant virtual machines and AWS EC2 instances.

The process for installing Salt and configuring it differs slightly depending on the platform. Vagrant instances use a masterless strategy and AWS instances use a master+minion strategy, however after the platform has been 'bootstrapped' the same instructions are used on both.

## Installing Salt

A project called [salt-bootstrap](https://github.com/saltstack/salt-bootstrap) is used to install Salt on both Vagrant and AWS EC2 minions. The builder script that does this is found here: `./scripts/bootstrap.sh`.

For AWS EC2, the builder commands `update` and `launch` upload and execute this script. If Salt is not detected or an older version is detected, `bootstrap.sh` will call the `salt-bootstrap` script with the correct parameters.

For Vagrant, the `vagrant up` and `vagrant provision` commands will run this script.

## Upgrading Salt

Salt works best when both the master and clients are running on the same version of Salt, however there is backwards support for older clients talking to newer masters.

The version of Salt used is found in the `defaults.salt` section of [your project file]( https://github.com/elifesciences/builder/blob/master/projects/example.yaml#L3). When an EC2 instance is created the version of Salt to install is included in the list of build-time data, called it's `context`. It's this value that is passed to the `bootstrap.sh` script that determines whether Salt needs upgrading or not.

Before you can upgrade the version of Salt on a minion:

1. update the version of Salt in your projects file
2. upgrade the Salt master with `./bldr master.update_salt_master`

and then:

3. upgrade the minion with `./bldr master.update_salt:project--iid`

Salt has been very stable with almost no problems upgrading `builder` instances from `2014.7` to `2015.8` to `2016.3` to `2017.8`.
