# master-server

The `builder` uses a master+minion configuration when used on AWS.

The `master-server` project instance *must* exist in AWS before other minions can
be told what their configuration is.

## deploying a master server for the first time

Deploy a new `master-server` instance with:

	PROJECT=master-server ./bldr deploy

It will prompt you for an identifier before proceeding.

The master server needs access to clone your [builder-private](https://github.com/elifesciences/builder-private-example) repo. This is done using [Github deploy keys](https://developer.github.com/guides/managing-deploy-keys/#deploy-keys).

Copy the contents of the *master server's* pubkey (`/root/.ssh/id_rsa.pub`) into a new deploy key for your `builder-private` repo.

Or, copy the output of the below command into the new deploy key (where 'something' is the name you gave your master-server instance):

    ssh-keygen -y -f ./.cfn/keypairs/master-server--something

Then run:

	INSTANCE=master-server--yourinstanceid ./bldr aws_update_stack

to complete the update.
