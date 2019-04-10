from collections import OrderedDict

ACCOUNT_EKS_AMI = '602401143452'

def generic_tags(context, name=True):
    tags = OrderedDict([
        ('Project', context['project_name']), # "journal"
        ('Environment', context['instance_id']), # "prod"
        ('Cluster', context['stackname']), # "journal--prod"
        # the name AWS Console uses to label an instance
        ('Name', context['stackname']), # "journal--prod"
    ])
    return tags
