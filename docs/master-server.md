# master-server

`builder` uses [Salt](https://saltproject.io) in a master+minion configuration to configure AWS EC2 instances.

The `master-server` project instance *must* exist in AWS before other minions can be told what their configuration is. 

The `master-server` project instance and Vagrant VMs are able to provision themselves ('masterless').

## deploying a master server for the first time

Deploy a new `master-server` production instance with:

    ./bldr launch:master-server,prod

The first attempt will fail as the master server cannot access the [builder-private](https://github.com/elifesciences/builder-private-example) repo.

This can be done using [Github deploy keys](https://developer.github.com/guides/managing-deploy-keys/#deploy-keys).

Download the new master server's public key with:

    ./bldr download_file:master-server--prod,/root/.ssh/id_rsa.pub,/tmp,use_bootstrap_user=True

Now add the contents of `/tmp/id_rsa.pub` as a read-only deploy key to your `builder-private` repository on Github.

Then run:

    ./bldr update:master-server--prod

to complete the update. All Salt states shown should be green.

## updating the master server

When a formula or the `builder-configuration` or `builder-private` repositories change the master server must be updated.

It will do so every hour through a cron job but can also be run immediately with:

    ./bldr master.update

This `master.update` will do a regular `./bldr update` first and then perform `master-server` specific tasks.
