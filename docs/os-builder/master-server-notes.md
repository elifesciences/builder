# master server server

## creation

a master server must be created in order to tell minions what to do.

bootstrap:
- author creates master server
- builder generates and downloads ec2 keypair using boto
- builder creates and launches master server cfn template
    - using the given keypair
    - TODO: elastic IP
- builder connects using key
- builder adds author's pub key to the ubuntu user's `allowed_users`
    - Salt knows which users have access to which projects
        - author always has access to the machines they have created
            - even if their access to a project has been rescinded later
- builder installs itself on master using author's git keys
    - builder will be an open project
    - credentials will *not* be
- builder configures the master server
    - your minion_id is `master-...`
    - this is your config
    - these are your salt instructions
    - call highstate
        - starts web server running
- master is now ready to start serving minions


generate key-pair using instance-id as name
download keypair to use for initial bootstrap
write keypair to S3
- DO NOT SHARE
    - only instance creator has access
    - only those in deploy user's allowed_keys has access.

create instance using instance-id and keypair with instance-id
once created:
    bootstrap salt
    set minion/master files
    ... ?


## authorization

it's not practical to have a sysadmin authorize the creation of all new minions

we need something with a little bit of logic between master and minion
- that knows which users are allowed to create which minion (project) types
- that provides an interface
    - "give me a list of projects"
    - "give me the project config for ..."
    - "give me the pillar data for ..."
    - is *fast* and *stable*
    - doesn't compromise the master server
        - performance
        - security
    - only available to users who can ssh in
        - ????
        - I was thinking of making requests to master.elife.internal
            - tunnel the requests through the master server
            - use a user that has no sudo access whatsoever
            - have the webserver manage this user's allowed_keys files
        - might be safer to run on a non-standard port?
        - 
    
