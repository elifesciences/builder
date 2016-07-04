#!/bin/bash
# run after Packer has finished running provisioners

# remove Salt's minion_id file
# not entirely sure where this file came from? wherever it came from, it 
# takes precedence over HOSTNAME which is what Vagrant bootstrap prefers.
sudo rm -f /etc/salt/minion_id
