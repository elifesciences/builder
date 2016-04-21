# elife-drupal

__This doc describes how the eLife Drupal website (elife-drupal) is used within 
the elife-builder project.__

## VPN

The VPN is always disabled. To enable the VPN service create the flag 
`vpn-enabled` (see the flags section below) and start the vpn service with 
`sudo service openvpn start`. When salt runs again, the service won't be 
disabled.

## Switching origins and branches

Often the point of deploying an elife-drupal instance is to see the results of 
work done in another branch or fork of the project. Doing this through Salt is
possible, but not recommended.

Once the elife-drupal instance has been launched with `fab aws_launch_instance`
use `fab switch_remote_origin` to switch to a fork of the project and 
`fab switch_branch` to switch to a particular branch. 

## Flags

Flags are empty files that live in the root user's home dir (`/root/`).

Flags can be created with `touch /root/<flagname>` as the root user.

Certain actions are not taken unless flagged explicitly to do so. The tasks may 
be time consuming, or dangerous, or complimentary or not particularly necessary.

Once a flag is set or removed, Salt (our configuration managment tool) can be
told to try again with:

    $ sudo salt-call state.highstate
    
## Database

The salt instructions for this can be found in `salt/salt/elife-drupal/init.sls`.

### downloading

The current behaviour of the `elife-builder` project is to download the database
dump from the Highwire FTP *UNLESS* it finds a file called 
`/opt/public/jnl-elife.sql`. This maps to `../elife-drupal/jnl-elife.sql` on the
host.

What works well for me is to make `jnl-elife.sql` a symlink to the current db
dump I want to use.

_NOTE_: There is an [outstanding enhancement request](https://trello.com/c/k6rLOa98/523-enhancement-elife-drupal-check-for-jnl-elife-sql-gz-gz-instead-of-raw-sql-file-we-don-t-want-random-sql-files-hanging-around-kee) 
from Ruth to have it check for the gzipped version instead and unpack the db 
while loading.

### loading 

The database is only ever loaded once as part of the initial build. To have the
database loaded again when `state.highstate` is run, delete the flag 
`journal-loaded.lock`.

    $ sudo rm /root/journal-loaded.lock
    $ sudo salt-call state.highstate

## downloading files

The files will __not__ be downloaded from the Highwire FTP unless the flag 
`flag-elife-drupal-download-files` is set. Size of download at last count was 
~300MB.

    $ sudo touch /root/flag-elife-drupal-download-files
    $ sudo salt-call state.highstate

## Solr

Solr is installed now as part of the base `elife-drupal` project. This may 
change and only become available in development installation, we'll see.

To have Solr configure itself to use a HW dump they have provided, extract a 
copy into the `public/` folder and Salt will link it in and restart Solr.

The path should look like `public/drupal_codev_jnl_elife/`

Solr admin can be accessed at `http://localhost:8983/solr/`
