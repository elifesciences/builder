# master-server

`builder` uses Salt in a master+minion configuration when used on AWS.

The `master-server` project instance *must* exist in AWS before other minions can
be told what their configuration is. All the EC2 instances will pull their configuration from the master, which is the only instance able to provision itself.

## deploying a master server for the first time

Deploy a new `master-server` instance with:

	./bldr launch:master-server,prod

The first attempt will fail as the master server cannot access your [builder-private](https://github.com/elifesciences/builder-private-example) repo. This can be done using [Github deploy keys](https://developer.github.com/guides/managing-deploy-keys/#deploy-keys):

    ./bldr download_file:master-server--prod,/root/.ssh/id_rsa.pub,/tmp,use_bootstrap_user=True
    # now add /tmp/id_rsa.pub as a read-only deploy key to your repository

Then run:

	./bldr update:master-server--prod

to complete the update. All Salt states shown should be green.
