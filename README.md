# builder

*TEMPORARY REPO WHILE ANY CREDENTIALS OR SENSITIVE INFORMATION IS CUT OUT*

An attempt to centralize the configuration and building of application environments at [eLife](https://elifesciences.org), locally (Vagrant) and remotely (AWS).

# first

Download:

	git clone ssh://git@github.com/elifesciences/builder

Install:

    ./update.sh

Fix any missing pre-requisites and call `./update.sh` again until you see the happy

> all done

message. Updating in the future is as simple as:

    git pull
    ./update.sh

## Next

Your `settings.yaml` file was created automatically and contains options for tweaking the behaviour of `builder`, like the project file it should be using.

By default it points to the `./projects/elife.yaml` project file. This file describes all eLife projects that can be built and their environments.

Project files and the `settings.yaml` file are the **only** two places where configuration is _supported_.

> 'configuration' also exists in `./src/buildercore/config.py` if you're a `builder` dev.

After successfully installing and configuring `builder`, launching a Vagrant instance is a good test that all is working correctly.

### Vagrant

The `Vagrantfile` can build any project, you just need to tell it which one.

This is done by selecting the project from the menu:

    $ vagrant up
    You must select a project:

    1 - journal--vagrant
    2 - api-gateway--vagrant
    3 - ...
    >

... or it can be done with environment variables:

    $ PROJECT=journal--vagrant vagrant up

The `--vagrant` suffix after the project name is the "instance-id" for that project and plays a larger role when bringing up project instances on AWS.

### AWS (Amazon Web Services)

The other half of the `builder` project is the ability to create and manage AWS resources. This is controlled with the "bldr" script:

    $ ./bldr -l

Will list all `builder` tasks found in `src/`. These tasks are just Python functions.

A `master-server` instance must exist before project instances can be brought up. [See here](docs/master-server.md) for a walkthrough.

To launch a project backed by a code repository to AWS:

    $ ./bldr deploy

To launch an ad-hoc instance of any project to AWS, use:

    $ ./bldr aws_launch_instance

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
