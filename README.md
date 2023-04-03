# builder

Centralised configuration and building of [eLife](https://elifesciences.org) *journal* applications locally ([Vagrant](#vagrant)) 
and remotely ([AWS, GCS](#aws-amazon-web-services)).

`builder` is a Python 3.8+ project and supports Linux and MacOS.

# installation

Download:

    git clone ssh://git@github.com/elifesciences/builder

Install (Linux, see [docs/osx.md](docs/osx.md) for macs).

    ./update.sh

Fix any missing pre-requisites and call `./update.sh` again until you see the 'all done' message.

Exclude *all* pre-requisite checks with `--exclude all`. For example:

    ./update.sh --exclude all

Exclude *specific* pre-requisite checks with `--exclude foo bar baz`. For example:

    ./update.sh --exclude virtualbox vault

Checked pre-requisites:

- git
- virtualenv
- make
- virtualbox
- vagrant
- ssh-credentials
- ssh-agent
- aws-credentials
- vault
- brew (MacOS only)
- openssl@1.1 (MacOS only)
- libffi (MacOS only)
- libssh2 (MacOS only)
- cmake (MacOS only)

# updating

    git pull
    ./update.sh

## configuration

The project file `./projects/elife.yaml` describes the eLife projects that can be built and their environments. 
[See here](docs/projects.md) for more project file documentation.

Multiple project files can be configured by copying `settings.yaml.dist` to `settings.yaml` and 
then modifying `project-files`.

After successfully installing and configuring `builder`, try launching a Vagrant machine to test all is working correctly:

    PROJECT=basebox vagrant up

## development

`builder` is a Python project and it's dependencies are captured in a `Pipfile`.

It's virtualenv is found in `./venv` and can be activated with `./venv/bin/activate`.

To update a dependency, modify the `Pipfile` and run `./update-dependencies.sh` to refresh the `Pipfile.lock` and 
`requirements.txt` files. You will need `pipenv` installed.

## testing

    ./test.sh

### Vagrant

The `Vagrantfile` can build any project:

    $ PROJECT=journal vagrant up

or use the menu:

    $ vagrant up
    You must select a project:

    1 - journal--vagrant
    2 - api-gateway--vagrant
    3 - ...
    >

The Vagrantfile will call a Python script to discover which projects are available. To execute that script with Docker:

    touch .use-docker.flag

Note: if you wish to use a private key not in `~/.ssh/id_rsa`, you can [customize the SSH key path](docs/ssh-key.md).

Note: if you wish to use a hypervisor other than `virtualbox`, you can use the `vagrant-mutate` plugin
to rebuild the ubuntu/trusty64 box for your own hypervisor. See the [vagrant and virtualbox documentation](docs/vagrant-and-virtualbox.md).

#### Working with formula branches in Vagrant

Project formulas are cloned to the local `./cloned-projects` directory and become shared directories within Vagrant. 

Changes to formulas including their branches are available immediately.

#### Working with project branches in Vagrant

Run the following command inside Vagrant to change the remote commit or branch:

    $ set_local_revision $commitOrBranch

Then apply the formula inside Vagrant with `sudo salt-call state.highstate` or from outside with `vagrant provision`.

### AWS (Amazon Web Services)

The other half of the `builder` project is the ability to create and manage AWS (Amazon Web Services) and 
GCP (Google Cloud Platform) resources. This is controlled with the `bldr` script:

    $ ./bldr -l

Will list all available tasks.

`builder` relies on a `~/.aws/credentials` file containing [configuration for accessing your AWS account](https://aws.amazon.com/blogs/security/a-new-and-standardized-way-to-manage-credentials-in-the-aws-sdks/).

A `master-server` instance must exist before project instances can be brought up. [See here](docs/master-server.md).

To create a project instance:

    $ ./bldr launch

Or specify a project and an instance ID directly with:

    $ ./bldr launch:journal,myinstanceid

To ssh into this project instance:

    $ ./bldr ssh:journal--myinstanceid

If the instance ID used matches the name of an *alternate config* (under 'aws-alt') in `./projects/elife.yaml` then 
that alternate configuration will be used.

Some alternate configurations are unique (like most `prod` configurations) and you won't be able to use that ID.

## More

General:
* [project files](docs/projects.md)

AWS:
* [feature: write keypairs to S3](docs/feature,write-keypairs-to-s3.md)
* [creating a master server](docs/master-server.md)
* [caveats](docs/caveats.md)
* [EKS](docs/eks.md)

Troubleshooting:

* [ssh-agent](docs/ssh-agent.md)
* [vault](docs/vault.md)

Development:

* [adding projects](docs/adding-projects.md)
* [technology](docs/tech.md)
* [salt](docs/salt.md)
* [testing](docs/testing.md)

## Copyright & Licence

The `builder` project is [MIT licenced](LICENCE.txt).
