#!/bin/bash
# lint our scripts
set -e
if which shellcheck &> /dev/null; then
    # shellcheck is installed! shellcheck is a shell script linter
    
    checkshell () {
        shell=$1
        echo "testing against $shell..."
        
        # disabled:
        # - SC1091: Not following: <script> was not specified as input (see shellcheck -x).
        
        shellcheck --shell=$shell ./scripts/*.sh -e SC1091
        shellcheck --shell=$shell ./*.sh -e SC1091
    }
    
    checkshell "bash"
    checkshell "sh"
    checkshell "dash"
    checkshell "ksh"

else
    echo "shellcheck not found! scripts NOT linted"
    echo "https://github.com/koalaman/shellcheck"
fi
