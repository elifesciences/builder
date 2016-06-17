# master-server

The `builder` uses a master-minion configuration when used on AWS.

A `master-server` project instance *must* exist in AWS before other minions can
be told what their configuration is.

## deploying a master server for the first time

There are some manual steps required after the `aws_launch_instance` of a
`master-server` project:

* copy the contents of /root/.ssh/id_rsa.pub into a new deploy key for the 
repository in the master server's `formula-repo` repository.
* run `aws_bootstrap` to complete the update


