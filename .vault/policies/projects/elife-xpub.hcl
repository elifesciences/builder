path "secret/data/projects/elife-xpub/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/*" {
    capabilities = ["list"]
}
