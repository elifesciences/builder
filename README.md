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

    $ PROJECT=elife-website-dev vagrant up

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


