# elife-bot

__This doc describes how the elife-bot is used within the elife-builder 
project.__

The elife-bot Salt configuration are in the `salt/salt/elife-bot/` directory and 
the config files are in `salt/salt/elife-bot/config/`.

## updating `settings.py`

The elife-bot settings.py file lives at 
`salt/salt/elife-bot/config/opt-elife-bot-settings.py`

Adding or changing these settings will requiring updating any instances you want
to see those changes reflected on (obviously).

The command to update an instance is:

    $ fab aws_update_stack
    
And then pick the instance you want to update. Instances are prefixed with their
project name, `elife-bot` in this case.

## updating elife-bot code

If changes have happened in the code and you want an instance running the latest
version of the elife-bot, you can:

1. use the `fab aws_update_stack` like above (__preferred__)

2. ssh into the server and run `sudo salt-call state.highstate` 

3. ssh into the server, `cd /opt/elife-bot` and do a `git pull`

## Notes

* to activate the virtualenv you need to `cd /opt/elife-bot/` and then 
`source venv/bin/activate`
* to run the `lettuce` tests you need to have the virtualenv running and then
`cd tests/ && lettuce`
* there appears to occasionally be a problem unzipping the files in time
while testing resulting in a 'file not found' type error. running the tests a
second time appears to fix that.
* There are *many* settings in settings.py and it's managed mostly by Graham, so 
for now I'm keeping the settings in there rather than splicing them out and into
the pillar data structure. 

