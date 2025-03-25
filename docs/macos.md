# Running on OSX

`builder` supports MacOS. Anything preventing `builder` from running on MacOS is a bug and an issue should be opened.

### Intel-based Macs

Install from dependancies with homebrew:

    brew install vagrant git openssl@1.1 libssh2 libffi python@3.10 vault virtualbox


Activate the Python virtual env:

    source ./venv/bin/activate


Then run the `./update.sh` script, which overrides a few of the build paths via environment variables to build correctly
from Homebrew installed libraries (to match libraries Python was built against).

    ./update.sh


### AppleSilicon/ARM-based Macs

Install from dependancies with homebrew:

    brew install vagrant git openssl@1.1 libssh2 libffi python@3.10 vault


Install developer preview version of virtualbox from https://www.virtualbox.org/wiki/Downloads

Activate the Python virtual env:

    source ./venv/bin/activate


Then run the `./update.sh` script, which overrides a few of the build paths via environment variables to build correctly
from Homebrew installed libraries (to match libraries Python was built against).

    ./update.sh


Note: if running on an M* ARM-based mac, you may need to run with the `TFENV_ARCH=amd64` env var set if using a terraform version earlier than 1.0.2:

    TFENV_ARCH=amd64 ./update.sh


You should now be able to run `./bldr` commands.
