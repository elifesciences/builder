# feature: write keypairs to s3

*Warning: this feature is not available outside of the eLife organization at the moment*

This feature is *enabled* by default.

When an ec2 instance is created a private+public keypair is also created that 
will allow SSH access to that instance. This file is written to the 
`.cfn/keypairs/` directory.

It's assumed the creator of an ec2 instance will always have access.

    ./bldr owner_ssh

Other members of the team can allow access to instances via the Salt 
configuration, associating users with their public keys to projects.

However, it may be desirable to have this keypair stored somewhere another can 
access it in case of calamity.

It's *not* desirable to allow just anybody to have access to this store of 
private keys. The below policy can be used to grant write-only access to users
of the builder to store the keys but not download them:

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "111",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:List*"
                ],
                "Resource": "arn:aws:s3:::bucketname/keypairs/*"
            }
        ]
    }

Obviously, if your users have blanket S3 permissions they'll be able to download
those keys regardless. 
