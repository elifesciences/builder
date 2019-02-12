path "secret/data/answer" {
    capabilities = ["read"]
}

path "secret/data/projects/*" {
    capabilities = ["read"]
}

path "secret/data/projects/" {
    capabilities = ["list"]
}
