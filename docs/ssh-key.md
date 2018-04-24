# custom ssh key

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
