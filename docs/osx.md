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

As mentioned, running builder natively on macOS can be hit a miss due to changes in builder, and painpoints of python on macOS from homebrew. This can run faster than the intel-based container above, and is much easier to setup the ssh-agent. These instructions should get you up and running.

Install from dependancies with homebrew:

```
brew install vagrant git openssl@1.1 libssh2 libffi python@3.8 # parallel-ssh fails to build again python > 3.8
```

Some other hashicorp dependancies require legacy versions right now - 0.11 for `terraform` and 0.11 for `vault`. You can install these globally, or local to just builder and set your path appropriately like so:

```
mkdir .bin
curl https://releases.hashicorp.com/terraform/0.11.15/terraform_0.11.15_darwin_amd64.zip -o terraform.zip && unzip ./terraform.zip -d .bin && rm ./terraform.zip
curl https://releases.hashicorp.com/vault/0.11.6/vault_0.11.6_darwin_amd64.zip -o vault.zip && unzip ./vault.zip -d .bin && rm ./vault.zip
export PATH="$(PWD)/.bin:$PATH"
```

Then run the `./update.sh` script, but overriding a few of the build paths to build correctly from homebrew installed libraries (to match libraries Python was built against)

```
OPENSSL_ROOT_DIR="$(brew --prefix openssl@1.1)" \
LDFLAGS="-L$(brew --prefix openssl@1.1)/lib -L$(brew --prefix libffi)/lib -L$(brew --prefix libssh2)/lib" \
CPPFLAGS="-I$(brew --prefix openssl@1.1)/include -I$(brew --prefix libffi)/include -I$(brew --prefix libssh2)/include" \
./update.sh --exclude virtualbox
```

(`--exclude virtualbox` is for M* ARM-based macs, as virtualbox is non-functional outside x86 platforms.)

You should now be able to run ./bldr commands.
