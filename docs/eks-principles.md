# EKS deployment principles

The scope of this document covers principles to follow when deploying applications to EKS inside the eLife AWS account.

EKS is a partially managed Kubernetes where AWS runs Kubernetes masters and provides an AMI to run a fleet of anonymous worker nodes that have to be create using EC2 APIs.

## Clusters

Multiple clusters allow a smaller blast radius: one configuration setting changing cannot take down the whole infrastructure. However they do increase the need for maintenance as these changes have to be propagated in multiple places. Moreover, they reduce cost optimization as hardware resources cannot be ([easily and safely](https://github.com/kubernetes-sigs/kubefed)) shared across clusters.

Therefore, maintain:

- a `test` cluster for all testing environments (`staging` but also `end2end` or `demo`)
- a `prod` cluster for all production environments (`prod` but also `preview`)

## Namespaces

Unclear yet whether we should use namespaces to isolate project and/or environments and/or teams from each other.

## Nodes

(Worker) nodes are not managed by EKS and are created with an autoscaling group that will.

Never try to SSH into nodes or to upgrade their software. Terminate them (preferably after cordoning and draining them so that nothing is running there) and they will be recreated by the autoscaling group maintaining a set number.

## Pods

Pods co-locate containers on the same node. Containers running in a Pod share also the same port space.

A Pod is a basic unit of horizontal scaling so don't mix containers that may need to run with a different number of replicas, unless you limit the project to a single Pod.

## Deployments

Pods are ephemeral and won't survive a node failure. Never create Pods directly for an application, but always create Deployments that manage the Pods for you.

## Load balancing

Use a Service to load balance traffic to identical Pods, whether the traffic is internal or external.

Use `LoadBalancer` Services for external traffic, or traffic from the VPC but outside the Kubernetes cluster.

Use `ClusterIp` Services for internal traffic, as they are cheaper and simpler. They are the equivalent of a private DNS name.

## DNS

TBD: no [creation of DNS](https://github.com/elifesciences/issues/issues/4572) at the moment.

## Secrets

TBD: no [Vault integration](https://github.com/elifesciences/issues/issues/4897) at the moment.

## Logging

TBD: no [external logging aggregator](https://github.com/elifesciences/issues/issues/4898) supported at the moment.

## Monitoring

TBD: no [monitoring](https://github.com/elifesciences/issues/issues/4899) supported at the moment.
