import requests
import os

def http_access(url):
    resp = requests.head(url, allow_redirects=True)
    return resp.status_code == 200

def ssh_access(url):
    cmd = 'git ls-remote ' + url + ' &> /dev/null'
    return os.system(cmd) == 0

def access(repo_url):
    bits = repo_url.split('://', 1)
    if len(bits) == 1:
        protocol = 'ssh'
        remote = repo_url
    else:
        assert len(bits) == 2, "could not find a protocol in url: %r" % repo_url
        protocol, remote = bits
    if protocol == 'http':
        protocol = 'https'
    return {
        'https': http_access,
        'ssh': ssh_access,
    }[protocol](remote)
