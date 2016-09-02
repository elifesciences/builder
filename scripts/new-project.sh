#!/bin/bash

set -e  # everything must pass
set -u  # no unbound variables
set -xv # show interpolation

pname=$1

mkdir -p ./cloned-projects/
cd ./cloned-projects/
git clone https://github.com/elifesciences/builder-example-project "$pname"
rm -rf "./$pname/.git/"
sed -i "s/#Example \$appname/$appname/g" README.md




exit


#!/bin/bash
set -e # everything must pass
set -u # no unbound variables
set -xv  # output the scripts and interpolated steps
appname=$1

rm -rf "$appname-formula"

if [ -d "$appname-formula" ]; then
    echo "directory $appname-formula already exists. quitting"
    exit 1
fi


cp -R builder-example-project $appname-formula
cd $appname-formula

rm -rf .git
rm README.md
rm salt/README.md
rm -rf salt/simple-project
rm salt/pillar/simple-project.sls
cp ../README.md ../LICENCE.txt .

ebuilder=/home/luke/dev/python/elife-builder

cp -RL $ebuilder/salt/salt/$appname salt/$appname
cp $ebuilder/salt/salt/top.sls salt/example.top
cp $ebuilder/salt/pillar/top.sls salt/pillar/top.sls
if [ -e $ebuilder/salt/pillar/$appname.sls ]; then
    cp $ebuilder/salt/pillar/$appname.sls salt/pillar/$appname.sls
else
    touch salt/pillar/$appname.sls
fi

cd salt
rm example.pillar
ln -s pillar/$appname.sls example.pillar
cd ..

echo "
base:
    '*':
        - elife
        - $appname" > ./salt/pillar/top.sls

git init
git add .
git ci -am "initial commit"

# replace any pillar.sys calls with pillar.elife calls
find salt/ -type f -exec sed -i 's/pillar\.sys\./pillar\.elife\./g' {} \;

# replace any pillar.monitor calls with pillar.logging calls
find salt/ -type f -exec sed -i 's/pillar\.monitor\./pillar\.elife\.logging\./g' {} \;

find salt/ -type f -exec sed -i 's/mysql_root\./db_root\./g' {} \;

# replace any pillar.elife.env calls with pillar.elife.FOO calls
# the logic needs to be adjusted
# UPDATE: decided to keep pillar.elife.env and deprecated pillar.elife.dev
#find salt/ -type f -exec sed -i 's/pillar\.elife\.env/pillar\.elife\.FOO/g' {} \;

# replace any logging.central_logging calls with logging.BAR calls
# these need to be REMOVED
find salt/ -type f -exec sed -i 's/logging\.central_logging/logging\.BAR/g' {} \;



# render the readme template
sed -i "s/\$appname/$appname/g" README.md

cp salt/pillar/$appname.sls /home/luke/dev/salt/builder-private/pillar/$appname.sls.new



