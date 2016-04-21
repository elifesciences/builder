# Synchronising elife-builder state

When a stack is created I want this stack available to other users of the 
elife-builder immediately. To this end certain files are stored on S3 and 
synchronised as needed.

The files being synched are:

* stack .json files and it's deploy user .pem and .pub files
* a copy of the `project/elife.yaml` file 

These files live in `./cfn/` (for CloudFormatioN).

The policy used for syncing stacks and other data so it can be shared between 
users without being committed to the repo is this:

when syncing:
    before operation, always copy down from S3, destructively (destroying any local changes not on s3)
    after operation, always copy up destructively (deleting any remote contents not on local)
    
problems with this policy:
* if content is added to s3 between the start and end of your operation, it will be deleted
* if the network is dropped during the task, any new content will not be synced back up.
