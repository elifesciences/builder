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
  ◕ ‿‿ ◕   all done

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

