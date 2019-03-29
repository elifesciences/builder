# EKS

EKS is the chosen implementation of Kubernetes: AWS manages the master nodes but not the worker nodes that run containers; those should be run in an autoscaling group that uses a standard AMI.

A project can be configured to create a cluster with the `eks` configuration in `elife.yaml`.

## User access

### Prerequisites

- Install [`kubectl`](https://kubernetes.io/docs/tasks/tools/install-kubectl/)
- Install [`aws-iam-authenticator`](https://docs.aws.amazon.com/eks/latest/userguide/install-aws-iam-authenticator.html)

### Configure kubectl

Make sure your AWS user is _either_:

- added to the `KubernetesAdministrators` group
- allowed to execute `eks:describeCluster`, and `sts:assumeRole` on `arn:aws:iam::512686554592:role/kubernetes-aws--test--AmazonEKSUserRole`

where `kubernetes-aws--test` is the name of the stack containing the cluster.

Execute:

```
$ aws eks update-kubeconfig --name=kubernetes-aws--test --role-arn arn:aws:iam::512686554592:role/kubernetes-aws--test--AmazonEKSUserRole
```

This will write a new configuration in `~/.kube/config`.

You can now execute:
```
$ kubectl version
$ kubectl get nodes
```
