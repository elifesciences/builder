#!/bin/bash
set -e
cd /
sudo mkdir -p /vagrant /srv/salt/ /srv/dev-pillar/ /srv/pillar/
sudo mount -t vboxsf vagrant /vagrant
sudo mount -t vboxsf salt-state /srv/salt/
sudo mount -t vboxsf salt-pillar /srv/pillar/
sudo mount -t vboxsf salt-dev-pillar /srv/dev-pillar/
