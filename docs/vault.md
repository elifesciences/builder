# vault

Vault is a tool for managing secrets, such as API keys and other credentials. In the context of builder, these credentials are mostly necessary to access or modify infrastructure.

## User scenario

builder assumes a logged-in Vault client, probably running on the master server.

Run the following command to log in:

`./bldr vault.login`

You should be asked for an access token that your system administrators should provide you with.

In case it's necessary to log out, run:

`./bldr vault.logout`

Terraform, wrapped by builder, will read the ~/.vault-token file during its operations.

## Creating new tokens

After logging in with a root token, run:

`./bldr vault.token_create`

This token will be associated with the `builder-user` policy which gives it read-only access to secrets needed by builder.

To lookup information about a token:

`./bldr vault.token_lookup:<token>`

To revoke a token:

`./bldr vault.token_revoke:<token>`
