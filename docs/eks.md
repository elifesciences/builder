# EKS

EKS is the chosen implementation of Kubernetes on AWS's elife account.

## User guide

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

### Configure Helm

Helm uses the same authentication as `kubectl` so no further credentials are required.

If you are running Helm for the first time, initialize your local configuration with:

```
helm init --client-only
```

## Chart developer guide

If you want to deploy an application to Kubernetes, you're going to use Helm to create a chart. Make sure you go through the [user guide](#user-guide) first to setup the tool.

### Create a new chart

TBD

### Test a chart

TBD

## Administrator guide

### Create a new cluster

A project can be configured to create a cluster with the `eks` configuration in `elife.yaml`.

### See the moving parts

builder generates Terraform templates that describe the set of EKS, EC2 and even some Helm-managed Kubernetes resources that are created inside an `eks`-enabling stack.

```
bldr update_infrastructure:kubernetes-aws--test  # will generate Terraform templates, they should have no change to apply
cat .cfn/terraform/kubernetes-aws--test.json | jq .
```

### See what's running

```
helm ls
kubectl get pods --all-namespaces
```

### AMI update

Workers are managed through an [autoscaling group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/AutoScalingGroup.html). When the AMI of the worker is updated, only newly created EC2 instances will use it; existing ones won't be deleted.

The best option to update the AMI is to cordon off servers, drain them and delete them so that they are recreated by the autoscaling group. This is not implemented in `builder`, but can be achieved with the commands:

```
kubectl get nodes       # 
kubectl cordon my-node  # no new Pods will be scheduled here
kubectl drain my-node   # existing Pods will be evicted and sent to another noe
aws ec2 terminate-instances --instance-ids=...  # terminate a node, a new one will be created
```
