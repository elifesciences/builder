# EKS deployment principles

The scope of this document covers principles to follow when deploying applications to EKS inside the eLife AWS account.

EKS is a partially managed Kubernetes where AWS runs Kubernetes masters and provides an AMI to run a fleet of anonymous worker nodes that have to be create using EC2 APIs.

## Clusters

Multiple clusters allow a smaller blast radius: one configuration setting changing cannot take down the whole infrastructure. However they do increase the need for maintenance as these changes have to be propagated in multiple places. Moreover, they reduce cost optimization as hardware resources cannot be ([easily and safely](https://github.com/kubernetes-sigs/kubefed)) shared across clusters.

## Namespaces

TBD: 

## Nodes

## Deployments

## Load balancing


## DNS

TBD: 

## Secrets

TBD: no Vault integration at the moment.

## Logging

TBD: no external logging aggregator supported at the moment.

## Monitoring

TBD: no monitoring supported at the moment.
