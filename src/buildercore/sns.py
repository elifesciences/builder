import hashlib
import json

# https://github.com/boto/boto/blob/develop/boto/sns/connection.py#L322
def subscribe_sqs_queue(sns_client, topic_arn, queueobj):
    """
    Subscribe an SQS queue to a topic.
    This is convenience method that handles most of the complexity involved
    in using an SQS queue as an endpoint for an SNS topic.  To achieve this
    the following operations are performed:
    * The correct ARN is constructed for the SQS queue and that ARN is
      then subscribed to the topic.
    * A JSON policy document is contructed that grants permission to
      the SNS topic to send messages to the SQS queue.
    * This JSON policy is then associated with the SQS queue using
      the queue's set_attribute method.  If the queue already has
      a policy associated with it, this process will add a Statement to
      that policy.  If no policy exists, a new policy will be created.
    :type topic_arn: string
    :param topic_arn: The ARN of the new topic.
    :type queueobj: A boto3 SQS Queue object
    :param queueobj: The queue object you wish to subscribe to the SNS Topic.
    """
    #q_arn = queue.arn
    q_arn = queueobj.attributes['QueueArn']

    # t = queue.id.split('/') # '/512686554592/exp-workflow-starter-queue' => exp-workflow-starter-queue
    # this is the boto3 equivalent, but `t` is unused
    # t = q_arn.rsplit(':', 1)[-1] # arn:aws:sqs:us-east-1:512686554592:exp-workflow-starter-queue => exp-workflow-starter-queue

    sid = hashlib.md5((topic_arn + q_arn).encode('utf-8')).hexdigest()
    sid_exists = False
    # resp = sns_`client.subscribe(topic_arn, 'sqs', q_arn)
    resp = sns_client.subscribe(TopicArn=topic_arn, Protocol='sqs', Endpoint=q_arn)

    #attr = queue.get_attributes('Policy')
    # if 'Policy' in attr:
    #    policy = json.loads(attr['Policy'])
    # else:
    #    policy = {}
    policy = queueobj.attributes.get('Policy', {})
    if policy:
        policy = json.loads(policy)

    if 'Version' not in policy:
        policy['Version'] = '2008-10-17'
    if 'Statement' not in policy:
        policy['Statement'] = []

    # See if a Statement with the Sid exists already.
    for s in policy['Statement']:
        if s['Sid'] == sid:
            sid_exists = True
    if not sid_exists:
        statement = {'Action': 'SQS:SendMessage',
                     'Effect': 'Allow',
                     'Principal': {'AWS': '*'},
                     'Resource': q_arn,
                     'Sid': sid,
                     'Condition': {'StringLike': {'aws:SourceArn': topic_arn}}}
        policy['Statement'].append(statement)

    #queue.set_attribute('Policy', json.dumps(policy))
    queueobj.set_attributes(Attributes={'Policy': json.dumps(policy)})

    return resp
