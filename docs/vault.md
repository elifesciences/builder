# vault

Vault is a tool for managing secrets, such as API keys and other credentials. In the context of builder, these credentials are mostly necessary to access or modify infrastructure.

## Command-line interface

### User scenario

To perform `update_infrastructure`, builder assumes a logged-in Vault client, probably running on the master server.

Run the following command to log in:

`./bldr vault.login`

You should be asked for an access token that your system administrators should provide you with.

In case it's necessary to log out, run:

`./bldr vault.logout`

Terraform, wrapped by builder, will read the ~/.vault-token file during its operations.

### Creating new tokens

After logging in with a root token, run:

`./bldr vault.token_create`

This token will be associated with the `builder-user` policy which gives it read-only access to secrets needed by builder.

To lookup information about a token:

`./bldr vault.token_lookup:<token>`

To revoke a token:

`./bldr vault.token_revoke:<token>`

### Reading and writing secrets (admin only)

Some commands can be manually run to directly interact with Vault's key-value secrets store:

```
$ VAULT_ADDR=https://master-server.elifesciences.org:8200 vault kv get secret/builder/apikey/fastly-gcs-logging
Key                 Value
---                 -----
email               fastly@elife-fastly.iam.gserviceaccount.com
secret_key          -----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

```
$ VAULT_ADDR=https://master-server.elifesciences.org:8200 vault kv put secret/builder/apikey/fastly-gcp-logging email=fastly@elife-fastly.iam.gserviceaccount.com secret_key=@../../fastly-gcp-logging.secret
Success! Data written to: secret/builder/apikey/fastly-gcp-logging
```

## Secrets for formulas

Non-`master-server` stacks can pull secrets from Vault through the Salt master, rather than from pillars:

| Virtual machine | Using Salt Master? | Can use Vault for secrets? |
| --------------- | ------------------ | -------------------------- |
| Vagrant         | Masterless         | No                         |
| EC2             | Masterful          | Yes                        |
| EC2             | Masterless         | Yes                        |

`master-server` stacks cannot depend on themselves during bootstrap, and hence can't use Vault:

| Virtual machine | Using Salt Master? | Can use Vault for secrets? |
| --------------- | ------------------ | -------------------------- |
| Vagrant         | Masterless?        | No                         |
| EC2             | Masterful          | No                         |
| EC2             | Masterless         | No                         |
