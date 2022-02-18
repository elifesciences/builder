#!/usr/bin/env python3

from distutils.version import StrictVersion
from shlex import split
import os, re, sys

MINIMUM_VERSION_TERRAFORM = StrictVersion('0.11.13')
MINIMUM_VERSION_VAULT = StrictVersion('0.11.0')

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

def terraform_version_checker(_cmd):
    installed_version = StrictVersion(shs('terraform --version').splitlines()[0].replace('Terraform v', '').strip())
    if not installed_version >= MINIMUM_VERSION_TERRAFORM:
        raise RuntimeError("Installed terraform version %s does not satisfy the minimum version requirement %s" % (installed_version, MINIMUM_VERSION_TERRAFORM))

    return str(installed_version)

def vault_version_checker(_cmd):
    installed_version = StrictVersion(re.match("Vault v([^ ]+)", shs('vault -version')).groups()[0])
    if not installed_version >= MINIMUM_VERSION_VAULT:
        raise RuntimeError("Installed vault version %s does not satisfy the minimum version requirement %s" % (installed_version, MINIMUM_VERSION_VAULT))

    return str(installed_version)

# Checks that need to be run on all operating systems.
both_checks = [
    ('git',
     {'Linux': 'apt-get install build-essential',
      'Mac OS': 'xcode-select --install'}),

    ('virtualenv',
     {'Linux': 'sudo pip install virtualenv',
      'Mac OS': 'brew install python@2'}),

    # needed for installing pynacl, which is a transitive dependency of Paramiko which is a dependency of Fabric
    ('make',
     {'Linux': 'apt-get install build-essential',
      'Mac OS': 'xcode-select --install'},
     dumb_install_check,
     lambda x: shs('make -v').splitlines()[0]),

    ('virtualbox',
     {'Mac OS': 'brew install --cask virtualbox'},
     dumb_install_check,
     lambda x: shs('vboxmanage --version')),

    ('vagrant',
     {'Mac OS': 'brew install --cask vagrant'}),

    ('ssh-credentials',
     {'all': 'ssh-keygen -t rsa'},
     lambda x: sh('test -f %s && test -f %s.pub' % (ssh_key, ssh_key)),
     None), # do not check version

    ('aws-credentials',
     {'all': 'do `aws configure` after installing builder'},
     lambda x: sh('test -f ~/.aws/credentials || test -f ~/.boto'),
     None),

    ('terraform',
     {'all': 'download from https://www.terraform.io/downloads.html'},
     lambda x: shs('which terraform'),
     terraform_version_checker),

    ('vault',
     {'all': 'download from https://www.vaultproject.io/downloads.html'},
     lambda x: shs('vault --version'),
     vault_version_checker),
]

# Checks that ONLY need to be run on Linux.
linux_checks = [
    ('ssh-agent',
     {'Linux': "echo 'eval $(ssh-agent); ssh-add;' >> ~/.bashrc && source ~/.bashrc"},
     lambda x: sh("ssh-add -L 2>&1 > /dev/null || [ $? -eq 1 ]"),
     None)
]

# Checks that ONLY need to be run on Mac OS.
mac_checks = [
    ('brew',
     {'Mac OS': '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"'},
     dumb_version_check,
     None),

    ('brew cask',
     {'Mac OS': 'brew tap caskroom/cask'},
     lambda x: sh('brew tap | grep homebrew/cask &> /dev/null'),
     None),

    ('ssh-agent',
     {'Mac OS': "echo 'Host *\n\tUseKeychain yes\n\tAddKeysToAgent yes\n' >> ~/.ssh/config && ssh-add -K %s" % ssh_key},
     lambda x: sh("ssh-add -L 2>&1 > /dev/null || [ $? -eq 1 ]"),
     None),

    # Needed to build ssh2-python
    ('cmake',
     {'Mac OS': "brew install cmake"},
     dumb_install_check,
     None)
]

def run_checks(check_list, exclusions=[]):
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

    exit(failed_checks)

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
    parser.add_argument('--exclude', dest='exclusions', nargs='+', type=str, default=[])
    args = parser.parse_args()

    run_checks(checks, args.exclusions)

if __name__ == '__main__':
    main()
