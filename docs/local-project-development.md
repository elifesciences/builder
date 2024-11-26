# Vagrant

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
to rebuild any `ubuntu/*` box in use for your own hypervisor. See the [vagrant and virtualbox documentation](docs/vagrant-and-virtualbox.md).

## A note on other hypervisors

`builder` currently relies on VirtualBox being available to orchestrate VM
builds using Vagrant.  On systems that already have a running hypervisor this
might not be desirable, since only one hypervisor can use virtualization
extensions at a time.  Since the main `ubuntu/*` images are only available as a
virtualbox image this makes the situation complicated.

Luckily a vagrant plugin named `vagrant-mutate` exists to work around this.  It
can convert vagrant boxes to different provider formats.  To install it locally
you can run:

```bash
$ vagrant plugin install vagrant-mutate
```

Now you can download the VirtualBox image and convert it to a format that your hypervisor can work with:

```bash
$ vagrant box add ubuntu/focal64 https://atlas.hashicorp.com/ubuntu/focal64
$ vagrant mutate --input-provider virtualbox ubuntu/focal64 <output-format> # libvirt, bhyve, kvm
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
==> medium--vagrant:  -- Base box:          ubuntu/focal64
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

# Lima (experimental)

Lima can be used directly as a hypervisor to build development VMs for the builder projects. This lightweight hypevisor is available on Linux and macOS, and relies on the qemu universe to virtualise machines. This also unlocks the ability to run VMs on and for a different architecture that intel, such as arm64.

Once lima and qemu is installed, you can create a dev VM using the `create-lima-dev-env` script:

```
./create-lima-dev-env iiif
```

If you run it without arguments, it will prompt for a project
```
> ./create-lima-dev-env
1) accepted-submission-cleaning 7) bus              13) elife-dashboard         19) exeter-kriya    25) iiif            31) observer                    37) task-adept
2) annotations                  8) containers       14) elife-libero-reviewer   20) fastly-logs     26) journal         32) pattern-library
3) api-gateway                  9) data-pipeline    15) elife-libraries         21) figure-viewer   27) journal-cms     33) profiles
4) basebox                      10) digests         16) elife-metrics           22) firewall        28) lax             34) recommendations
5) bastion                      11) elife-alfred    17) elife-reporting         23) generic-cdn     29) master-server   35) redirects
6) bioprotocol                  12) elife-bot       18) error-pages             24) heavybox        30) monitor         36) reproducible-document-stack
Select a project:
```

You can enter the project by name or number.

This will cloned the configured formulas, create and configure the VM, and run a first `sudo salt-call state.apply` (equivalent to highstate) within the VM. It will automatically map any ports >1024 to the host, so that you can access your services on localhost:8080 for example. Builder directory is mounted as /builder, and salt is configured to use the correct formulas from `cloned-projects` there.

To enter the VM, you can run `limactl shell dev-env`. This will open a bash shell inside the VM, adn you a free to run `salt-call` as needed.

start, stop and delete the VM using the `limactl` tool.

You can further customise the machine by setting lima configuration values in `projects/elife.yaml` under the `lima:` key, including remapping ports (particularly below port 1024) to your host, setting RAM and CPUs, and other bahaviours (such as forcing architecture or activating rosetta functionality on AppleSilicon macos). See lima documentation for more details.

# Working with formula branches in Vagrant or lima

Project formulas are cloned to the local `./cloned-projects` directory and become shared directories within Vagrant or lima VMs.

Changes to formulas including their branches are available immediately.

You can switch or create branches locally, then apply the formula inside Vagrant with `sudo salt-call state.highstate` or from outside with `vagrant provision`.
