# EKS

EKS is the chosen implementation of Kubernetes: AWS manages the master nodes but not the worker nodes that run containers; those should be run in an autoscaling group that uses a standard AMI.

A project can be configured to create a cluster with the `eks` configuration in `elife.yaml`.

## User access

### Prerequisites

- Install [`kubectl`](https://kubernetes.io/docs/tasks/tools/install-kubectl/)
- Do not install `aws-iam-authenticator`: it's [no longer necessary](https://docs.aws.amazon.com/cli/latest/reference/eks/get-token.html) in recent versions of the `aws` CLI

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

## AMI update

Workers are managed through an [autoscaling group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/AutoScalingGroup.html). When the AMI of the worker is updated, only newly created EC2 instances will use it; existing ones won't be deleted.

The best option to update the AMI is to cordon off servers, drain them and delete them so that they are recreated by the autoscaling group. This is not implemented in `builder`.
