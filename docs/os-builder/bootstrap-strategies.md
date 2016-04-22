## bootstrap strategy 1   "shared everything"

this is what we currently have.

all users can access all servers
    - even master server
    - all users can sudo

to bootstrap a minion:

    user tells builder to create/deploy an instance
    builder tells master to generate keys
    master generates and accepts keys
    builder downloads keys from master
    builder creates minion
    builder installs salt-minion
    builder sets minion's keys
    builder starts salt-minion
    minion attempts to connect master
    minion receives configuration
    minion provisions self

this is *very* convenient

this is *very* insecure



## bootstrap strategy 2   "minion pull"

no regular user can access the master server

when a user is added to a project
- they are given an IAM permission to read stack files from an s3 bucket
    - grants them access to create/update/delete project instances
- their public key is added to those project instances
    - grants them ssh access to all project instances

when a user is removed from a project
- their IAM read permission to the S3 bucket is removed
    - losing create/update/delete access to those project instances
- their public key is revoked from those project instances
    - removes their ssh access to all those project instances


bootstrapping:

    user tells builder to create/deploy an instance
    builder deposits stack file in S3
    master receives notification of new minion
    master generates and accepts keys
    master uploads minion keys to S3
    builder polls s3 until minion keys exist
    builder receives keys
    builder creates minion
    builder installs salt-minion
    builder sets minion's keys
    builder starts salt-minion
    minion attempts to connect master
    minion receives configuration
    minion provisions self

way more secure

much more complex
    - requires something to manage user to project permissions
        - these are not the same permissions as github repo project

