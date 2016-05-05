#!/usr/bin/env python

from __future__ import print_function
import os, sys

def sh(cmd):
    return os.system(cmd) == 0

def shs(cmd):
    from subprocess import Popen, PIPE
    stdout, stderr = Popen(cmd.split(), stdout=PIPE).communicate()
    if stderr:
        raise RuntimeError(stderr)
    return stdout.decode('utf-8').strip()

def dumb_install_check(cmd):
    return sh('which %s &> /dev/null' % cmd)

def dumb_version_check(cmd):
    return shs(cmd + ' --version')

def osx():
    return sh("test $(uname) == 'Darwin'")

BOTH_CHECKS = [
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

    ('aws credentials',
     {'all': 'do `aws configure` after installing elife-builder'},
     lambda x: sh('test -f ~/.aws/credentials || test -f ~/.boto'),
     None), # do not check version
]

MAC_CHECKS = [
    ('brew',
     {'osx': 'ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"'}),
     
    ('brew cask',
     {'osx': 'brew install caskroom/cask/brew-cask'},
     lambda x: sh('which brew &> /dev/null && brew list | grep brew-cask')
    ),
]

def check_cmd(cmd):
    installed_checker = dumb_install_check
    version_checker = dumb_version_check

    if len(cmd) == 2:
        cmd, install_suggestions = cmd
    elif len(cmd) == 3:
        cmd, install_suggestions, installed_checker = cmd
    elif len(cmd) == 4:
        cmd, install_suggestions, installed_checker, version_checker = cmd

    c_cmd = cmd.replace(' ', '_')

    sys.stdout.write('* %r ... ' % cmd)
    ret = False
    if installed_checker(c_cmd):
        found = 'found'
        if version_checker:
            found = version_checker(c_cmd)
        sys.stdout.write(found)
        ret = True
    else:
        sys.stdout.write('NOT found.')
        suggestions = install_suggestions.items() if install_suggestions else None
        if suggestions:
            sys.stdout.write(' Try:\n')
            for opsys, suggestion in install_suggestions.items():
                print('   %s: %s' % (opsys, suggestion))
    sys.stdout.write('\n')
    sys.stdout.flush()
    return cmd, ret
    
def run_checks(check_list):
    return [check_cmd(cmd) for cmd in check_list]

def main():
    checks = BOTH_CHECKS
    if osx():
        print('OSX detected')
        checks += MAC_CHECKS
    if False in map(lambda p: p[1], run_checks(checks)):
        exit(1)
    exit(0)

if __name__ == '__main__':
    main()
