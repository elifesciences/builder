# builder

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

If you are outside of the eLife organization, make sure to set the `write-context-to-s3` and `write-keypairs-to-s3` keys in `settings.yml` keys are `False`. Their use is related to backing up information about the generated resources on an S3 bucket, but the customization of this bucket is not supported yet.

## Next

Your project file is located at `./projects/elife.yaml`. This file describes all eLife projects that can be built and their environments. [See here](docs/projects.md) for more project file documentation.

> 'configuration' also exists in `./src/buildercore/config.py` if you're a `builder` dev.

After successfully installing and configuring `builder`, launching a Vagrant instance is a good test that all is working correctly.

### Vagrant

The `Vagrantfile` can build any project, you just need to tell it which one:

    $ vagrant up
    You must select a project:

    1 - journal--vagrant
    2 - api-gateway--vagrant
    3 - ...
    >

... or it can be done with environment variables:

    $ PROJECT=journal vagrant up

To execute the Python part of the Vagrantfile with Docker, create this flag:

```
touch .use-docker.flag
```

Note: if you with to use a private key not in `~/.ssh/id_rsa`, you can [customize the SSH key path](docs/ssh-key.md).

Note: if you wish to use a hypervisor other than `virtualbox`, you can use the `vagrant-mutate` plugin
to rebuild the ubuntu/trusty64 box for your own hypervisor.  See the [vagrant and virtualbox documentation](docs/vagrant-and-virtualbox.md).

#### Working with formula branches

Formula projects are cloned to the local _cloned-projects_ directory. Changes will be picked up from there and branches can be used as well.

#### Working with project branches

After starting (`vagrant up`) and login in to (`vagrant ssh`) the VM, run the following command to change the remote commit or branch:

    $ set_local_revision $commitOrBranch

Provisioning (`vagrant provision` or `sudo salt-call state.highstate`) will then checkout the particular commit or branch.

### AWS (Amazon Web Services)

The other half of the `builder` project is the ability to create and manage AWS resources. This is controlled with the "bldr" script:

    $ ./bldr -l

Will list all builder tasks found in `src/`. These tasks are just Python functions.

builder relies on a `~/.aws/credentials` file containing [configuration for accessing your AWS account](https://aws.amazon.com/blogs/security/a-new-and-standardized-way-to-manage-credentials-in-the-aws-sdks/).

A `master-server` instance must exist before project instances can be brought up. [See here](docs/master-server.md) for a walkthrough.

To launch a project backed by a code repository to AWS:

    $ ./bldr deploy
    // or specify project and environment
    $ ./bldr deploy:journal,prod

To launch a instance of any project to AWS, use:

    // or specify project and environment
    $ ./bldr launch:api-gateway,prod

To ssh into one of these machines:

    $ ./bldr ssh:journal--prod

## More!

General:
* [project files](docs/projects.md)

AWS:
* [feature: write keypairs to S3](docs/feature,write-keypairs-to-s3.md)
* [creating a master server](docs/master-server.md)
* [caveats](docs/caveats.md)

Troubleshooting:

* [ssh-agent](docs/ssh-agent.md)
* [vault](docs/vault.md)

Development

* [adding projects](docs/adding-projects.md)
* [technology](docs/tech.md)
* [salt](docs/salt.md)
* [testing](docs/testing.md)

## Copyright & Licence

The `builder` project is [MIT licenced](LICENCE.txt).

The `builder` project was GPL3 licensed until [this commit](https://github.com/elifesciences/builder/commit/2fd91c1cc86efad92a4f40caa93837960baa4855) on 2016-07-13.
