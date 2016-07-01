# builder

*TEMPORARY REPO WHILE ANY CREDENTIALS OR SENSITIVE INFORMATION IS CUT OUT*

An attempt to centralize the configuration and building of application 
environments, locally (Vagrant) and remotely (AWS).

Test that you have the system prerequisites installed:

    ./prerequisites.py

It's up to you to install/update/configure anything missing.

It's assumed `brew` and `brew cask` are being used on OSX.

To install:

    git clone ssh://git@github.com/elifesciences/builder
    cd builder
    ./update.sh

To update:

    git pull
    ./update.sh

To test:

    ./test.sh

## Vagrant Usage

The `Vagrantfile` can build any project, you just need to tell it which one.

This is done by selecting the project from the menu:

    $ vagrant up
    You must select a project:

    1 - elife-website-dev
    2 - elife-crm-dev
    3 - ...
    > 

... or it can be done with environment variables:

    $ PROJECT=elife-website--dev vagrant up

NOTE: the __dev__ suffix after the project name.

## Amazon Web Services (AWS)

The other half of the builder project is the ability to create and manage AWS 
resources.

    $ ./bldr --list
    
Will list all builder tasks found in `src/`.

To launch a project backed by a code repository to AWS, use:

    $ ./bldr deploy

To launch an ad-hoc instance of any project to AWS, use:

    $ ./bldr aws_launch_instance


## CAVEATS

####### caveats


creating a master requires a token to clone the builder-private repo
- this token requires a public key
-- upload private key to root user [done]
-- generate a pub key [done]
-- create a github deploy key [todo]

builder-private must be kept synchronised with individual projects
- might be solvable with dynamic top files

builder-private pillar data is not always being updated
- problem with a lock files
    - https://github.com/saltstack/salt/issues/32888
- possibly problem with minion cache
    - https://github.com/saltstack/salt/issues/24050
- probably waiting for refresh interval of ~60 seconds

builder-base-formula pillar must be kept synchronized with the builder-private elife pillar

master rejects minion keys if one already exists
- this can be solved by running this on master
    # salt-key -d minionid

## More!

Further documentation can be found

Use cases:

* [Creating a new project for development](docs/basic-usage.md#creating-a-new-project-for-development)
* [Deploying a project instance remotely](docs/basic-usage.md#deploying-a-new-project-remotely)

Topics:

* [testing](docs/testing.md)
* [technology](docs/1-tech.md)
* [projects file](docs/projects.md)
* [creating, launching & accessing AWS instances](docs/basic-usage.md)
* [syncronising builder state](docs/syncing.md)
* [using packer to create baseboxes](docs/packer.md)
* [debugging errors](docs/errors.md)

Per-project documentation (as it relates to `elife-builder`) can be found here:

* [central-logging](docs/central-logging.md)
* [elife-api](docs/elife-api.md)
* [elife-bot](docs/elife-bot.md)
* [elife-ci](docs/elife-ci.md)
* [elife-civiapi](docs/elife-civiapi.md)
* [elife-drupal](docs/elife-drupal.md)
* [lagotto](docs/lagotto.md)

## Copyright & Licence

Copyright 2016 eLife Sciences. Licensed under the [GPLv3](LICENCE.txt)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
