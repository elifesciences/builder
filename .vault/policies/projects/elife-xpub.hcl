# runtime secrets for the application
path "secret/data/projects/elife-xpub/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

# build secrets
path "secret/data/containers/elife-xpub/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/*" {
    capabilities = ["list"]
}
