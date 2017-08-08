# custom ssh key

builder relies on a keypair (private and public key) being present at `~/.ssh/id_rsa` and `~/.ssh/id_rsa.pub`.

If you with to use a different path, specify the private key path as the CUSTOM_SSH_KEY environment variable in your vagrant commands:

```
CUSTOM_SSH_KEY=~/.ssh/my_key ./update.sh
CUSTOM_SSH_KEY=~/.ssh/my_key vagrant up
```

The corresponding public key, which is used to access the virtual machine through SSH, is assumed to be at `${CUSTOM_SSH_KEY}.pub`.
