# builder

Configuration management for [eLife](https://elifesciences.org) *journal* applications locally ([Vagrant](#vagrant)) 
and remotely ([AWS, GCS](#aws-amazon-web-services)).

`builder` is a Python project and supports Linux and MacOS.

It is responsible for:

* provisioning: creating cloud resources.
* automation: installing and configuring software on virtual machines.
* discovery: inspecting and accessing project resources.
* deployment: modifying project instances by changing application versions.

It depends on:

* [Vagrant](https://www.vagrantup.com/) for creating, running and managing *local* [Virtualbox](https://www.virtualbox.org/) project instances.
* [Amazon AWS services](http://aws.amazon.com/) for creating, running and managing *remote* project instances.
* [AWS CloudFormation](http://aws.amazon.com/cloudformation/) and [Hashicorp Terraform](...) for describing project instances.
* [Salt](http://saltstack.com/), for configuring project instances within Vagrant and AWS EC2.

## installation

Download:

    git clone ssh://git@github.com/elifesciences/builder

Install:

    ./update.sh

Specific requisites can be ignored with `--exclude foo bar baz`. For example:

    ./update.sh --exclude virtualbox vault

Exclude *all* requisites with `--exclude all`.

Checked requisites:

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

## updating

    git pull
    ./update.sh

## project configuration

The file `./projects/elife.yaml` describes eLife projects that can be built and their environments.

### project file structure

At the top of a project file is the 'defaults' section for all projects.

All other sections are 'projects'.

Each project inherits the settings found in 'defaults'. If a project setting isn't found, the value from the `defaults` section is used.

Some sections can (typically) be excluded by using `false` or `null`. For example:

    `aws.ec2: False`

Will exclude a default section from a project.

Display the final settings for any project with:

    $ ./bldr project.data

### default and alternate configurations

All projects have default Vagrant, AWS, and GCP configurations, typically in a minimal just-works configuration.

When launching a project instance with `./bldr launch:arg1,arg2,arg3`, the third parameter may specify the 'alt' configuration to use. For example:

    ./bldr launch:journal,my-stack,prod

will launch a `journal` project called `my-stack` with the `aws-alt` configuration named `prod`.

If the 3rd argument is omitted and the new stack's name matches an alternate config, the matching alt config will be used:

    ./bldr launch:journal,prod

will launch a `journal` project called `prod` with the `aws-alt` configuration named `prod`.

If a `journal--prod` exists, the stack cannot be created.

If an alternate config is marked as `unique`, it can only be used once.

## new projects





## project formula

The builder requires all projects to adhere to a certain directory structure. The `builder-example-project` can be found [here](https://github.com/elifesciences/builder-example-project).

Essentially, everything the `builder` needs is contained within the `salt` directory. This structure makes what SaltStack calls a *formula*. Examples of other, official, formulas can be found [here](https://github.com/saltstack-formulas).

Your actual project can continue living at the root of the repo (so long as it doesn't use the `salt` directory for it's own purposes) *or* your project can live in it's own repository completely separate from the formula.

> This doc won't go into how to use Salt and assumes from here on out you have a well formed project formula.

## builder project file

`builder` comes with two 'project' files. These files list the projects made available by the organisation. Your project will need an entry in here.

> If you don't have a project file yet, copy the `example.yaml` file and replace the settings for `project1` with your own.

Your project entry requires a `formula-repo` key whose value should be a path to the git repository your project formula lives in.

Much more detail about the project file can be found [here](docs/projects.md).

## Vagrant

You can now bring up instances of your project with:

	vagrant up

and choosing your project from the list, or

	PROJECT=yourprojectname vagrant up

to avoid the menu.

## AWS

Vagrant runs within a masterless environment without the organisation's secret credentials. This makes it very easy to simply clone (using the `formula-repo` value) and provision.

To deploy your application to AWS however requires a few more steps.

In your `builder-private` repository ([example here](https://github.com/elifesciences/builder-private-example)):

1. add your project to the list of [`gitfs_remotes`](https://github.com/elifesciences/builder-private-example/blob/master/etc-salt-master#L49)
2. update the *state* [`top.sls`](https://github.com/elifesciences/builder-private-example/blob/master/salt/top.sls) file with the contents of your `example.top` file.
3. if necessary, update the *pillar* [`top.sls`](https://github.com/elifesciences/builder-private-example/blob/master/pillar/top.sls) with an entry for your pillar file.
4. if step 3, then drop a copy of your `example.pillar` file into the [`./pillar/` directory](https://github.com/elifesciences/builder-private-example/tree/master/pillar).

Then update your `master-server` project instance with:

	./bldr update_master

# ---


# ---



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

Note: if you wish to use a private key not in `~/.ssh/id_rsa`, you can customize the SSH key path.

# ---

## Default

builder relies on a keypair (private and public key) being present at `~/.ssh/id_rsa` and `~/.ssh/id_rsa.pub`.

If you with to use a different path, specify the private key path as the CUSTOM_SSH_KEY environment variable in your commands:

```
CUSTOM_SSH_KEY=~/.ssh/my_key ./update.sh
```

The corresponding public key, which is used to access the virtual machine through SSH, is assumed to be at `${CUSTOM_SSH_KEY}.pub`.

## Vagrant

Vagrant will use your private key to authenticate with Github and checkout repositories through the SSH protocol

```
CUSTOM_SSH_KEY=~/.ssh/my_key vagrant up
CUSTOM_SSH_KEY=~/.ssh/my_key vagrant provisioning
```

## EC2

builder mainly interacts with EC2 through a custom key kept in `.cfn/keypairs`, which is synchronized using the state S3 bucket.

The `./bldr ssh` command allows the user to open an interactive SSH session on a node, and will use the user's key. It accepts `CUSTOM_SSH_KEY`:

```
CUSTOM_SSH_KEY=~/.ssh/my_key ./bldr ssh
```

# ---

# feature: write keypairs to s3

*Warning: this feature is not available outside of the eLife organization at the moment*

This feature is *enabled* by default.

When an ec2 instance is created a private+public keypair is also created that 
will allow SSH access to that instance. This file is written to the 
`.cfn/keypairs/` directory.

It's assumed the creator of an ec2 instance will always have access.

    ./bldr owner_ssh

Other members of the team can allow access to instances via the Salt 
configuration, associating users with their public keys to projects.

However, it may be desirable to have this keypair stored somewhere another can 
access it in case of calamity.

It's *not* desirable to allow just anybody to have access to this store of 
private keys. The below policy can be used to grant write-only access to users
of the builder to store the keys but not download them:

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "111",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:List*"
                ],
                "Resource": "arn:aws:s3:::bucketname/keypairs/*"
            }
        ]
    }

Obviously, if your users have blanket S3 permissions they'll be able to download
those keys regardless. 

# ---











# ---


Note: if you wish to use a hypervisor other than `virtualbox`, you can use the `vagrant-mutate` plugin
to rebuild the ubuntu/trusty64 box for your own hypervisor.


# ---

# vagrant and virtualbox

`builder` currently relies on VirtualBox being available to orchestrate VM
builds using Vagrant.  On systems that already have a running hypervisor this
might not be desirable, since only one hypervisor can use virtualization
extensions at a time.  Since the `ubuntu/trusty64` image is only available as a
virtualbox image this makes the situation complicated.

Luckily a vagrant plugin named `vagrant-mutate` exists to work around this.  It
can convert vagrant boxes to different provider formats.  To install it locally
you can run:

```bash
$ vagrant plugin install vagrant-mutate
```

Now you can download the VirtualBox image and convert it to a format that your hypervisor can work with:

```bash
$ vagrant box add ubuntu/trusty64 https://atlas.hashicorp.com/ubuntu/trusty64
$ vagrant mutate --input-provider virtualbox ubuntu/trusty64 <output-format> # libvirt, bhyve, kvm
```

Now you can disable the `virtualbox` check when running update.sh and run vagrant up:

```bash
$ ./update.sh --exclude="virtualbox"

  ...
  all done

$ PROJECT=medium vagrant up
 [info] hostname is medium--vagrant (this affects Salt configuration)
formulas needed: ["https://github.com/elifesciences/builder-base-formula", "https://github.com/elifesciences/medium-formula"]
Updating cloned-projects/builder-base-formula...
remote: Counting objects: 10, done.
remote: Compressing objects: 100% (7/7), done.
remote: Total 10 (delta 3), reused 9 (delta 3), pack-reused 0
Unpacking objects: 100% (10/10), done.
From https://github.com/elifesciences/builder-base-formula
   0fa3592..9295540  master     -> origin/master
Updating 0fa3592..9295540
Fast-forward
 elife/jenkins-scripts/colorize.sh | 6 ++++++
 1 file changed, 6 insertions(+)
 create mode 100755 elife/jenkins-scripts/colorize.sh

Cloning cloned-projects/medium-formula...
Cloning into 'cloned-projects/medium-formula'...
remote: Counting objects: 230, done.
remote: Compressing objects: 100% (11/11), done.
remote: Total 230 (delta 1), reused 9 (delta 1), pack-reused 218
Receiving objects: 100% (230/230), 27.10 KiB | 0 bytes/s, done.
Resolving deltas: 100% (83/83), done.
Checking connectivity... done.

Bringing machine 'medium--vagrant' up with 'libvirt' provider...
==> medium--vagrant: Creating image (snapshot of base box volume).
==> medium--vagrant: Creating domain with the following settings...
==> medium--vagrant:  -- Name:              builder_medium--vagrant
==> medium--vagrant:  -- Domain type:       kvm
==> medium--vagrant:  -- Cpus:              1
==> medium--vagrant:  -- Memory:            512M
==> medium--vagrant:  -- Management MAC:    
==> medium--vagrant:  -- Loader:            
==> medium--vagrant:  -- Base box:          ubuntu/trusty64
==> medium--vagrant:  -- Storage pool:      default
==> medium--vagrant:  -- Image:             /var/lib/libvirt/images/builder_medium--vagrant.img (40G)
==> medium--vagrant:  -- Volume Cache:      default
==> medium--vagrant:  -- Kernel:            
==> medium--vagrant:  -- Initrd:            
==> medium--vagrant:  -- Graphics Type:     vnc
==> medium--vagrant:  -- Graphics Port:     5900
==> medium--vagrant:  -- Graphics IP:       127.0.0.1
==> medium--vagrant:  -- Graphics Password: Not defined
==> medium--vagrant:  -- Video Type:        cirrus
==> medium--vagrant:  -- Video VRAM:        9216
==> medium--vagrant:  -- Keymap:            en-us
==> medium--vagrant:  -- TPM Path:          
==> medium--vagrant:  -- INPUT:             type=mouse, bus=ps2
==> medium--vagrant:  -- Command line : 
==> medium--vagrant: Creating shared folders metadata...
==> medium--vagrant: Starting domain.
==> medium--vagrant: Waiting for domain to get an IP address...
```

# ---










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

A `master-server` instance must exist before project instances can be brought up.

# ---


# master-server

`builder` uses [Salt](https://saltproject.io) in a master+minion configuration to configure AWS EC2 instances.

The `master-server` project instance *must* exist in AWS before other minions can be told what their configuration is. 

The `master-server` project instance and Vagrant VMs are able to provision themselves ('masterless').

## deploying a master server for the first time

Deploy a new `master-server` production instance with:

    ./bldr launch:master-server,prod

The first attempt will fail as the master server cannot access the [builder-private](https://github.com/elifesciences/builder-private-example) repository.

This can be done using [Github deploy keys](https://developer.github.com/guides/managing-deploy-keys/#deploy-keys).

Download the new master server's public key with:

    ./bldr download_file:master-server--prod,/root/.ssh/id_rsa.pub,/tmp,use_bootstrap_user=True

Now add the contents of `/tmp/id_rsa.pub` as a read-only deploy key to your `builder-private` repository on Github.

Then run:

    ./bldr update:master-server--prod

to complete the update. All Salt states shown should be green.

## updating the master server

When a formula or the `builder-configuration` or `builder-private` repositories change the master server must be updated.

It will do so every hour through a cron job but can also be run immediately with:

    ./bldr master.update

This `master.update` will do a regular `./bldr update` first and then perform `master-server` specific tasks.


# ---




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

AWS:
* [EKS](docs/eks.md)

# Troubleshooting:

## ssh-agent

`ssh-agent` is a program that holds private SSH keys so that they can be used for while logged in into other machines, either remote or local (virtual machines in this case).

builder uses ssh-agent to allow your SSH key to be used inside the Vagrant VMs it creates.

ssh-agent is *not* used for AWS instances instead by builder as it is not necessary: the instances have their own credentials for accessing e.g. Github. An exception is represented by the `bastion` server, but you don't need to use builder to connect to that.

## Troubleshooting

Check you have an ssh-agent running:
```
ps faxww | grep ssh-agent
```
should show at least one process.

If not, run
```
eval $(ssh-agent)
ssh-add
```

This should start an ssh-agent process and add your private key to it.

Inside a virtual machine or the `bastion` server, you can run:
```
$ env | grep SSH_AUTH_SOCK
SSH_AUTH_SOCK=/tmp/ssh-3DZzwm2FDF/agent.2040
```
to check the presence of this environment variable.

From the same place, you can also run:
```
$ ssh git@github.com
PTY allocation request failed on channel 0
Hi giorgiosironi! You've successfully authenticated, but GitHub does not provide shell access.
Connection to github.com closed.
```
to check that you can authenticate on Github using your own machine's SSH key.

Many formulas require to be able to check out repositories through the Git over SSH protocol.

# ---


Development:

* [salt](docs/salt.md)
* [testing](docs/testing.md)

## Copyright & Licence

The `builder` project is [MIT licenced](LICENCE.txt).

