# elife-civiapi

This project is the bridge between the elife-drupal website and the CiviCRM 
instance running at crm.elifesciences.org

## production (elife-civiapi)

After the elife-civiapi package is installed, the script 
`/usr/local/bin/mailcivi` is run via cron using a wrapper at 
`/usr/local/bin/mailcivi.sh`.

## development (elife-civiapi-dev)

The development configuration contains the elife-civiapi code at 
`/opt/elife-civiapi/` with a virtualenv at `/opt/elife-civiapi-virtualenv/`.

To switch to the elife-civiapi virtualenv, do:

    $ . /opt/elife-civiapi-virtualenv/bin/activate
    
## running tests

Tests can be run after the virtualenv has been activated using `lettuce`:

    $ cd /opt/elife-civiapi/tests/
    $ lettuce
