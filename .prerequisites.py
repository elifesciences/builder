#!/usr/bin/env python

from distutils.version import StrictVersion
from shlex import split
import os, sys

MINIMUM_VERSION_TERRAFORM = StrictVersion('0.11.7')

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

def osx():
    return sh('[ "$(uname)" = "Darwin" ]')

ssh_key = os.environ.get('CUSTOM_SSH_KEY', '~/.ssh/id_rsa')

def terraform_version_checker(_cmd):
    installed_version = StrictVersion(shs('terraform --version').replace('Terraform v', ''))
    if not installed_version >= MINIMUM_VERSION_TERRAFORM:
        raise RuntimeError("Installed terraform version %s does not satisfy the minimum version requirement %s" % (installed_version, MINIMUM_VERSION_TERRAFORM))

    return str(installed_version)

both_checks = [
    ('git',
     {'osx': 'brew install git'}),

    ('virtualenv',
     {'all': 'sudo pip install virtualenv'}),

    # needed for installing pynacl, which is a transitive dependency of Paramiko which is a dependency of Fabric
    ('make',
     {'all': 'which make'},
     dumb_install_check,
     lambda x: shs('make -v').splitlines()[0]),

    ('virtualbox',
     {'osx': 'brew cask install virtualbox'},
     dumb_install_check,
     lambda x: shs('vboxmanage --version')),

    ('vagrant',
     {'osx': 'brew cask install vagrant'}),

    ('ssh-credentials',
     {'all': 'ssh-keygen -t rsa'},
     lambda x: sh('test -f %s && test -f %s.pub' % (ssh_key, ssh_key)),
     None), # do not check version

    ('ssh-agent',
     {'all': "echo 'eval $(ssh-agent); ssh-add;' >> ~/.bashrc && source ~/.bashrc"},
     lambda x: sh('ps aux | grep ssh-agent$ > /dev/null'),
     None),

    ('aws-credentials',
     {'all': 'do `aws configure` after installing builder'},
     lambda x: sh('test -f ~/.aws/credentials || test -f ~/.boto'),
     None),

    (
        'terraform',
        {'all': 'download from https://www.terraform.io/downloads.html'},
        lambda x: shs('which terraform'),
        terraform_version_checker
    ),
]

mac_checks = [
    ('brew',
     {'osx': 'ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"'}),

    ('brew cask',
     {'osx': 'brew tap caskroom/cask'},
     lambda x: sh('brew cask help')
     ),
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
    if osx():
        print('OSX detected')
        checks = mac_checks + checks

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--exclude', dest='exclusions', nargs='+', type=str, default=[])
    args = parser.parse_args()

    run_checks(checks, args.exclusions)

if __name__ == '__main__':
    main()
