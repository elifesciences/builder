# Running on OSX

`builder` supports MacOS. Anything preventing `builder` from running on MacOS is a bug and an issue should be opened.

### AppleSilicon/ARM-based Macs

Install from dependancies with homebrew:

    brew install vagrant git openssl@1.1 libssh2 libffi mise

Activate the Python virtual env:

    source ./venv/bin/activate

Then run the `./update.sh` script, which overrides a few of the build paths via environment variables to build correctly
from Homebrew installed libraries (to match libraries Python was built against).

    ./update.sh

You should now be able to run `./bldr` commands.
