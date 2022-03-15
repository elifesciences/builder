# Running on OSX

Due to the underlying dependencies, it can be a bit hit and miss using `builder` on OSX. This can be worked around by running `builder` inside a container with the correct dependencies installed.

```
./mac-bldr.sh
```

Once started...

```
./update.sh --exclude virtualbox
```

Depending on the commands you intend to run, you might also need to login into `vault`.

```
./bldr vault.login
```

You should then be able to run any command you need to.

If you use a different SSH key, or your AWS credentials are stored in a non-standard location then use the `CUSTOM_SSH_KEY` and `CUSTOM_AWS_CREDENTIALS` environment variables to point at the right files, e.g.

```
CUSTOM_SSH_KEY=/path/to/ssh/key CUSTOM_AWS_CREDENTIALS=/path/to/aws/credentials/file ./mac-bldr.sh
```

## Running natively

As mentioned, running builder natively on macOS can be hit a miss due to changes in builder primarily targetting linux, and the painpoints of running modern python on macOS from homebrew. However, it can run faster than the intel-based container above, and is much easier to setup with an existing ssh-agent. These instructions should get you up and running.

Install from dependancies with homebrew:

```
brew install vagrant git openssl@1.1 libssh2 libffi python@3.8 # parallel-ssh fails to build again python > 3.8
```

As of now, a legacy version (v0.11) of hashicorp terraform is required. We also run a legacy version of `vault` (v0.11) on the server-side (though the newer clients maintain a level of backwards compatibility with older server APIs). You can install these versions globally, or local to just builder and set your path appropriately like so:

```
mkdir .bin
curl https://releases.hashicorp.com/terraform/0.11.15/terraform_0.11.15_darwin_amd64.zip -o terraform.zip && unzip ./terraform.zip -d .bin && rm ./terraform.zip
curl https://releases.hashicorp.com/vault/0.11.6/vault_0.11.6_darwin_amd64.zip -o vault.zip && unzip ./vault.zip -d .bin && rm ./vault.zip
export PATH="$(PWD)/.bin:$PATH"
```

Then run the `./update.sh` script, which overrides a few of the build paths via Environment Variables to build correctly from homebrew installed libraries (to match libraries Python was built against)

```
./update.sh --exclude virtualbox
```

(`--exclude virtualbox` is for M* ARM-based macs, as virtualbox is non-functional outside x86 platforms.)

You should now be able to run ./bldr commands.
