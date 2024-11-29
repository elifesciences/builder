#!/usr/bin/env python3

from shlex import split
import os, re, sys

try:
    # the recommended drop-in replacement but requires installation of 'packaging':
    # - https://packaging.pypa.io/en/latest/index.html
    from packaging.version import Version
    # 'setuptools' should also work:
    # - https://setuptools.pypa.io/en/latest/userguide/distribution.html#specifying-your-project-s-version
    # but requires installation of 'setuptools':
    # - https://setuptools.pypa.io/en/latest/userguide/quickstart.html#installation
except ImportError:
    # deprecated in Python 3.10, planned removal in Python 3.12, you'll get a warning.
    from distutils.version import StrictVersion as Version

MINIMUM_VERSION_VAULT = Version('0.11.0')

def sh(cmd):
    return os.system(cmd) == 0

def shs(cmd):
    from subprocess import Popen, PIPE
    try:
        stdout, stderr = Popen(split(cmd), stdout=PIPE).communicate()
    except OSError as e:
        raise RuntimeError("Cannot run command `{0}`".format(cmd), e)
    if stderr:
        raise RuntimeError(stderr)
    return stdout.decode('utf-8').strip()

def dumb_install_check(cmd):
    return sh('which %s &> /dev/null' % cmd)

def dumb_version_check(cmd):
    return shs(cmd + ' --version')

ssh_key = os.environ.get('CUSTOM_SSH_KEY', '~/.ssh/id_rsa')

def vault_version_checker(_cmd):
    installed_version = Version(re.match("Vault v([^ ]+)", shs('vault -version')).groups()[0])
    if not installed_version >= MINIMUM_VERSION_VAULT:
        raise RuntimeError("Installed vault version %s does not satisfy the minimum version requirement %s" % (installed_version, MINIMUM_VERSION_VAULT))

    return str(installed_version)

# Checks that need to be run on all operating systems.
both_checks = [
    ('git',
     {'Linux': 'apt-get install build-essential',
      'Mac OS': 'xcode-select --install'}),

    # lsh@2022-08-30: consider removing
    ('virtualenv',
     {'Linux': 'sudo pip install virtualenv',
      'Mac OS': 'brew install python@3.8'}),

    ('ssh-credentials',
     {'all': 'ssh-keygen -t rsa'},
     lambda x: sh('test -f %s && test -f %s.pub' % (ssh_key, ssh_key)),
     None), # do not check version

    ('ssh-agent',
     {'Linux': "echo 'eval $(ssh-agent); ssh-add;' >> ~/.bashrc && source ~/.bashrc",
      'Mac OS': "echo 'Host *\n\tUseKeychain yes\n\tAddKeysToAgent yes\n' >> ~/.ssh/config && ssh-add -K %s" % ssh_key},
     # Checks for a successful connection to the SSH agent, but allows for empty identity list.
     lambda x: sh("ssh-add -L 2>&1 > /dev/null || [ $? -eq 1 ]"),
     None),

    ('aws-credentials',
     {'all': 'do `aws configure` after installing builder'},
     lambda x: sh('test -f ~/.aws/credentials || test -f ~/.boto'),
     None),

    ('vault',
     {'all': 'download from https://www.vaultproject.io/downloads.html'},
     lambda x: shs('vault --version'),
     vault_version_checker),
]

# Checks that ONLY need to be run on Linux.
linux_checks = [
]

# Checks that ONLY need to be run on Mac OS.
mac_checks = [
    ('brew',
     {'Mac OS': '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"'},
     dumb_version_check,
     None),

    # Needed to build ssh2-python and cryptography python modules
    ('openssl@1.1',
     {'Mac OS': "brew install openssl@1.1"},
     lambda x: sh('brew ls | grep openssl@1.1 > /dev/null'),
     None),
    ('libffi',
     {'Mac OS': "brew install libffi"},
     lambda x: sh('brew ls | grep libffi > /dev/null'),
     None),
    ('libssh2',
     {'Mac OS': "brew install libssh2"},
     lambda x: sh('brew ls | grep libssh2 > /dev/null'),
     None),
    ('cmake',
     {'Mac OS': "brew install cmake"},
     dumb_install_check,
     None)
]

def run_checks(check_list, exclusions=[]):

    if 'all' in exclusions:
        return 0

    failed_checks = 0
    for cmd in check_list:
        installed_checker = dumb_install_check
        version_checker = dumb_version_check

        if len(cmd) == 2:
            cmd, install_suggestions = cmd
        elif len(cmd) == 3:
            cmd, install_suggestions, installed_checker = cmd
        elif len(cmd) == 4:
            cmd, install_suggestions, installed_checker, version_checker = cmd

        if cmd in exclusions:
            continue

        sys.stdout.write('* %r ... ' % cmd)
        if installed_checker(cmd):
            found = 'found'
            if version_checker:
                found = version_checker(cmd)
            if isinstance(found, bool):
                sys.stdout.write('ok\n')
            else:
                sys.stdout.write(found + '\n')
        else:
            sys.stdout.write('NOT found. Try:\n')
            for opsys, suggestion in install_suggestions.items():
                print('   %s: %s' % (opsys, suggestion))
            failed_checks = failed_checks + 1
        sys.stdout.flush()

    return failed_checks

def main():
    checks = both_checks
    platform = sys.platform
    if platform.startswith('linux'):
        print('Linux detected')
        checks = linux_checks + checks
    elif platform == 'darwin':
        print('Mac OS detected')
        checks = mac_checks + checks
    else:
        print('Unsupported platform \'%s\'' % platform)

    import argparse
    parser = argparse.ArgumentParser()
    choices = [check[0] for check in checks] + ['all']
    parser.add_argument('--exclude', **{
        'dest': 'exclusions',
        'nargs': '+',
        'type': str,
        'default': [],
        #'choices': choices, # good idea, but I want a more lenient check
        'help': "Exclude specific checks.",
    })
    args = parser.parse_args()

    unknown_exclusions = set(args.exclusions) - set(choices)
    if unknown_exclusions:
        print("WARNING: unknown exclusions will be ignored: %s" % ",".join(sorted(unknown_exclusions)))
        print("supported exclusions: %s" % ",".join(sorted(choices)))

    return run_checks(checks, args.exclusions)

if __name__ == '__main__':
    exit(main())
