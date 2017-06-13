# SaltStack

The `builder` project uses [SaltStack](https://github.com/saltstack/salt) to provision Vagrant and AWS instances.

The process for installing Salt and configuring it differs slightly depending on the platform, Vagrant instances use a masterless strategy and AWS instances use a master+minion strategy, however after the platform has been 'bootstrapped' the same instructions are used on both.

## Installing Salt

A project called [salt-bootstrap](https://github.com/saltstack/salt-bootstrap) is used to install Salt on both Vagrant and AWS minions. The script that does this is called `bootstrap.sh` and can be [found here](https://github.com/elifesciences/builder/blob/master/scripts/bootstrap.sh) in the `./scripts/` directory.

## Salt version

To change the version of Salt used by `builder`, use the `salt` key in [your project file]( https://github.com/elifesciences/builder/blob/master/projects/example.yaml#L3). The value of this key is used in the bootstrap script to [compare against the installed version of Salt](https://github.com/elifesciences/builder/blob/master/scripts/bootstrap.sh#L29) and upgrade if necessary.

It *is* possible to have different versions of Salt installed per-project on either Vagrant or AWS. Vagrant runs master-less and is a good place to test Salt upgrades per-project, however **it is not** recommended for AWS. For the sake of sanity, the master and minion versions of Salt should match on AWS.

Salt has been very stable with almost no problems upgrading `builder` instances from `2014.7` to `2015.8` to `2016.3.4`.

## Salt targeting Vagrant instances

Configuration specific to Vagrant instances can be done by using the `pillar.elife.dev` configuration.

`pillar.elife.dev` is `True` [out of the box](https://github.com/elifesciences/builder-base-formula/blob/master/pillar/elife.sls#L5) and should be overriden with `False` in the [builder-private](https://github.com/elifesciences/builder-private-example/blob/master/pillar/elife.sls#L7) repo.
