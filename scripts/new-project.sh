#!/bin/bash

set -e  # everything must pass
set -u  # no unbound variables
set -xv # show interpolation

appname=$1

cd ./cloned-projects

# rough check formula doesn't already exist
if [ -d "$appname-formula" ]; then
    echo "directory $appname-formula already exists. quitting"
    exit 1
fi

# create/update example project
if [ ! -d "builder-example-project" ]; then
    git clone https://github.com/elifesciences/builder-example-project
else
    (
        cd builder-example-project || exit
        git reset --hard
        git pull
    )
fi

cp -R builder-example-project "$appname-formula"
cd "$appname-formula"

rm -rf .git
rm README.md
rm salt/README.md
rm -rf salt/simple-project
rm salt/pillar/simple-project.sls

cp .README.template README.md
rm .README.template

(
    # jump into the formula's 'salt' root as a subshell (else shell lint cries)
    cd salt || exit

    # create an empty state file
    mkdir "$appname"
    #touch "$appname/init.sls"
    echo "echo 'hello, world':
    cmd.run" > "$appname/init.sls"

    # generate an example top salt file
    echo "base:
    '*':
        - elife
        - $appname" > ./example.top

    # replace the example.pillar file with a generated+empty one
    rm example.pillar
    echo "$appname:
    no: data" > "./pillar/$appname.sls"
    ln -s "./pillar/$appname.sls" example.pillar

    # generate an example top pillar file
    echo "base:
    '*':
        - elife
        - $appname" > ./pillar/top.sls
)

# init the repo
git init
git add .
git ci -am "initial commit"

# render the readme template
sed -i "s/\$appname/$appname/g" README.md

