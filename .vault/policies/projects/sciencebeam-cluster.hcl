# runtime secrets for the application
path "secret/data/projects/sciencebeam-cluster/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/*" {
    capabilities = ["list"]
}
