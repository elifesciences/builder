def generic_tags(context, name=True):
    tags = {
        'Project': context['project_name'], # "journal"
        'Environment': context['instance_id'], # "prod"
        'Cluster': context['stackname'], # "journal--prod"
    }
    # the name AWS Console uses to label an instance
    tags['Name'] = context['stackname'] # "journal--prod"
    return tags

