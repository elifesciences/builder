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
- make
- virtualbox
- vagrant or lima
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

After successfully installing and configuring `builder`, try launching a virtual machine to test all is working correctly. You can use Vagrant:

    PROJECT=basebox vagrant up

or lima

    ./lima create-dev

## development

`builder` is a Python project and it's dependencies are captured in a `Pipfile`.

It's virtual env is found in `./venv` and can be activated with `./venv/bin/activate`.


## testing

    ./test.sh

### Building projects locally

See [docs/local-project-development.md](docs/local-project-development.md) for more details on how to use vagrant or lima environments

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
