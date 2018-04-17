# master-server

`builder` uses Salt in a master+minion configuration when used on AWS.

The `master-server` project instance *must* exist in AWS before other minions can be told what their configuration is. All the EC2 instances will pull their configuration from the master, which is the only instance able to provision itself.

## deploying a master server for the first time

Deploy a new `master-server` instance with:

	./bldr launch:master-server,prod

The first attempt will fail as the master server cannot access your [builder-private](https://github.com/elifesciences/builder-private-example) repo. This can be done using [Github deploy keys](https://developer.github.com/guides/managing-deploy-keys/#deploy-keys).

Download the new master server's public key with:

    ./bldr download_file:master-server--prod,/root/.ssh/id_rsa.pub,/tmp,use_bootstrap_user=True

Now add the contents of `/tmp/id_rsa.pub` as a read-only deploy key to your `builder-private` repository on Github.

Then run:

	./bldr update:master-server--prod

to complete the update. All Salt states shown should be green.

## updating the master server

Whenever a change is made to the formulas, or to your `builder-private` repository, or a minion is destroyed, the master server needs to be updated. It will do so every hour through a cron job but can also be run immediately with:

	./bldr master.update:master-server--prod

This `master.update` will do a regular `update` first but then perform any master-server specific tasks.

## replacing the master server

The first step in replacing a master server is to launch a new instance. 

In the presence of multiple master servers, `builder` will sort them alphanumerically and prefer the first instance it finds. `master-server--a` would take precendence over `master-server--b` and `master-server--2001-01-01` would take precendence over `master-server--2012-12-12`.

All existing minions have the address for their master-server encoded in their `context` data and `build_vars`. The process of getting an existing minion to talk to a new master is called *re-mastering*.

Once the new master server has been properly created and configured it should be ready to command new minions out of the box.

To re-master a single minion:

    ./bldr master.remaster:project--ci,master-server--newinstanceid
    
To re-master *all* minions:

    ./bldr master.remaster_all:master-server--newinstanceid
    
The process of re-mastering a minion roughly follows:

* ensure new `aws.ec2.master_ip` value is shared with your team to avoid accidental regressions during migration
* replace the value of `aws.ec2.master_ip` in the `context` data
* refresh the `build_vars` with this new data
* remove the old master server's public key from the minion
* call `update` on the stack

easy! if the minion successfully starts it's highstate (part of `update`) then the minion is talking to the new master.

