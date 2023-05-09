# Running on OSX

`builder` supports MacOS. Anything preventing `builder` from running on MacOS is a bug and an issue should be opened.

That said, `builder` is developed, tested and used daily on Linux, not MacOS.

## Running in a container

Problems running `builder` on MacOS often come from the the underlying dependencies. These dependencies are captured in `.prerequisites.py` that are checked when `update.sh` is run.

If these dependency problems can't be resolved then `builder` can be run inside a container by running:

    ./mac-bldr.sh

Inside a running instance:

    ./update.sh --exclude virtualbox

(`--exclude virtualbox` is for M* ARM-based macs, as Virtualbox doesn't work outside x86 platforms.)

Depending on the commands you intend to run, you might also need to login into `vault`.

    ./bldr vault.login

You should then be able to run any command you need to.

If you use a different SSH key, or your AWS credentials are stored in a non-standard location then use the 
`CUSTOM_SSH_KEY` and `CUSTOM_AWS_CREDENTIALS` environment variables to point at the right files, e.g.

    CUSTOM_SSH_KEY=/path/to/ssh/key CUSTOM_AWS_CREDENTIALS=/path/to/aws/credentials/file ./mac-bldr.sh

## Running natively

`builder` will run faster outside of the intel-based container above and is much easier to setup with an existing 
ssh-agent. These instructions should get you up and running.

Install from dependancies with homebrew:

    brew install vagrant git openssl@1.1 libssh2 libffi python@3.8

An older version of `vault` (v0.11) is run on the server-side (though the newer clients maintain a level of backwards
compatibility with older server APIs). You can install these versions globally, or local to just builder and set your 
path appropriately like so:

```
mkdir .bin
curl https://releases.hashicorp.com/vault/0.11.6/vault_0.11.6_darwin_amd64.zip -o vault.zip 
unzip ./vault.zip -d .bin
rm ./vault.zip
export PATH="$(PWD)/.bin:$PATH"
```

Activate the Python virtualenv:

    source ./venv/bin/activate

Then run the `./update.sh` script, which overrides a few of the build paths via environment variables to build correctly 
from Homebrew installed libraries (to match libraries Python was built against).

    ./update.sh --exclude virtualbox

(`--exclude virtualbox` is for M* ARM-based macs, as Virtualbox doesn't work outside x86 platforms.)

You should now be able to run `./bldr` commands.
