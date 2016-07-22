#!/bin/bash
sudo hostname "$PROJECT"
sudo sh -c "echo ${PROJECT} > /etc/hostname"
