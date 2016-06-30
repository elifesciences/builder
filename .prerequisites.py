#!/usr/bin/env python

from __future__ import print_function
import os, sys

def sh(cmd):
    return os.system(cmd) == 0

def shs(cmd):
    from subprocess import Popen, PIPE
    try:
        stdout, stderr = Popen(cmd.split(), stdout=PIPE).communicate()
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
    return sh("test $(uname) == 'Darwin'")

both_checks = [
    ('git',
     {'osx': 'brew install git'}),
     
    ('virtualbox',
     {'osx': 'brew cask install virtualbox'},
     dumb_install_check,
     lambda x: shs('vboxmanage --version')),
     
    ('vagrant',
     {'osx': 'brew cask install vagrant'}),
     
    ('ssh credentials',
     {'all': 'ssh-keygen -t rsa'},
     lambda x: sh('test -f ~/.ssh/id_rsa && test -f ~/.ssh/id_rsa.pub'),
     None), # do not check version

    ('ssh-agent',
     {'all': "echo 'eval $(ssh-agent); ssh-add;' >> ~/.bashrc && source ~/.bashrc"},
     lambda x: sh('ps aux | grep ssh-agent$ > /dev/null'),
     None),
     
    ('aws credentials',
     {'all': 'do `aws configure` after installing elife-builder'},
     lambda x: sh('test -f ~/.aws/credentials || test -f ~/.boto'),
     None), # do not check version
]

mac_checks = [
    ('brew',
     {'osx': 'ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"'}),
     
    ('brew cask',
     {'osx': 'brew install caskroom/cask/brew-cask'},
     lambda x: sh('which brew &> /dev/null && brew list | grep brew-cask')
    ),
]

def run_checks(check_list, exclusions=[]):
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
            sys.stdout.write(found + '\n')
        else:
            sys.stdout.write('NOT found. Try:\n')
            for opsys, suggestion in install_suggestions.items():
                print('   %s: %s' % (opsys, suggestion))
        sys.stdout.flush()

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
