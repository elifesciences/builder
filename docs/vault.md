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

### Creating child tokens

```
vault token create -display-name=elife-alfred-exploratory-test-master-server -policy=master-server
```

`policy` here limits the policies attached to the child token, which would be inherited from the current token otherwise.


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

### AppRoles

AppRoles are a way for applications or their formula to integrate with Vault via a fixed set of credentials: role and secret are akin to username and password. These fixed credentials can be used to issue a temporary token.

```
vault write auth/approle/role/jenkins policies=default,jenkins-elife-alfred,master-server
```

`policies` specifies the policies this role will attach to its tokens. However, `role_id` and `secret_id` need to be stored into the application that will make use of them.

```
vault read auth/approle/role/jenkins/role-id
```
reads the `role-id` from the AppRole.

```
vault write -f auth/approle/role/jenkins/secret-id
```
creates a new `secret-id` for the AppRole.


### Periodic tokens

Periodic tokens allow an issued Vault token to essentially never expire, hence are useful for applications or formulas that for simplicity need to store a token without updating it for a long time.

Create a periodic token:
```
vault token create -display-name=periodic-token-example -policy=master-server -period=1h
```

This token will expire in 1 hour unless a renewal is performed:

```
VAULT_TOKEN=$(cat periodic.vault-token) vault token renew
```

This should be in a cron job and is only suitable for servers that are always alive to perform the renewal.

You can check the remaining time with:

```
VAULT_TOKEN=$(cat periodic.vault-token) vault token lookup
```

## Secrets for formulas

Non-`master-server` stacks can pull secrets from Vault through the Salt master, rather than from pillars:

| Virtual machine | Using Salt Master? | Can use Vault? | Which Vault?  |
| --------------- | ------------------ | -------------- | ------------- |
| Vagrant         | Masterless         | No             | -             |
| EC2             | Masterful          | Yes            | master-server |
| EC2             | Masterless         | No             | -             |

`master-server` stacks cannot depend on themselves during bootstrap, and hence can't use Vault:

| Virtual machine | Using Salt Master? | Can use Vault? | Which Vault?- |
| --------------- | ------------------ | -------------- | ------------- |
| Vagrant         | Masterless?        | No             | -             |
| EC2             | Masterful          | Only for tests | Itself        |
| EC2             | Masterless         | Only for tests | Itself        |

## Builder secrets dependencies

```
VAULT_ADDR=https://master-server.elifesciences.org:8200 vault kv list secret/builder/apikey
```
gives the following:

- `fastly`: API key for Fastly `it-admin@elifesciences.org` user, with permission to modify the CDN
- `fastly-gcp-logging`: API key for Fastly to write logs to GCP (BigQuery)
- `fastly-gcs-logging`: API key for Fastly to write logs to GCS (Google Cloud Storage buckets)
- `gcp`: JSON credentials for the `builder@elife-infrastructure.iam.gserviceaccount.com` Service Account
- `github`: Github token for accessing private repositories
