# ssh-agent

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
