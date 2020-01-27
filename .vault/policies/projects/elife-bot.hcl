# runtime secrets for the application
path "secret/data/projects/elife-bot/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/*" {
    capabilities = ["list"]
}
