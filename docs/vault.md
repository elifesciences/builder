# vault

Vault is a tool for managing secrets, such as API keys and other credentials. In the context of builder, these credentials are mostly necessary to access or modify infrastructure.

## User scenario

builder assumes a logged-in Vault client, probably running on the master server.

Run the following command to log in:

```
# from projects/elife.yaml, `defaults.aws.vault`
VAULT_ADDR=https://master-server.elifesciences.org:8200 vault login
```

You should be asked for an access token that your system administrators should provide you with.

In case it's necessary to log out, run:

```
rm ~/.vault-token
```

Terraform, wrapped by builder, will read the ~/.vault-token file during its operations. There is no need to keep providing the `VAULT_ADDR` environment variable after login, as builder contains the address in its configuration.

## Creating new tokens

After logging in with a root token, run:

```
VAULT_ADDR=<ADDRESS> vault token create -policy=builder-user -display-name=NameSurname
```

This token will be associated with the `builder-user` policy which gives it read-only access to secrets needed by builder.

To lookup information about a token:

```
VAULT_ADDR=<ADDRESS> VAULT_TOKEN=<TOKEN> vault token lookup
```

To revoke a token:

```
VAULT_ADDR=<ADDRESS> vault token revoke <TOKEN>
```
