# master server server

## creation

a master server must be created in order to tell minions what to do.

the creation of the master server currently lives in `srv/cfn.py` as `aws_create_master`. It uses the deploy user in the shared-everything strategy, installs a copy of the elife-builder and bootstraps itself.

convenient, yes, secure, no no no.

I want:
- any person to be able to create a master server
- BUT, that master server to be limited in what it can do based on the author
    - so it requires a creator with enough permissions to make it usable

I see master server creation being the only hardcoded project in new builder.

bootstrap:
- author creates master server
- builder generates and downloads ec2 keypair using boto
- builder creates and launches master server cfn template
    - using the given keypair
    - elastic IP
- builder connects using key
- builder adds author's pub key to the ubuntu user's `allowed_users`
- builder installs itself on master using author's git keys
- builder configures the master server
    - your minion_id is `master`
    - this is your config
    - these are your salt instructions
    - call highstate
        - starts web server running
- master is now ready to start serving minions


## authorization

it's not practical to have a sysadmin authorize the creation of all new minions
- in some cases it might be, but not this one

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
    
