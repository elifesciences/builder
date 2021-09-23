"Bit of a floating module, I guess to avoid circular dependencies. Needs to be reconciled somehow."

from . import bluegreen, bluegreen_v2, context_handler, cloudformation

def concurrency_for(stackname, concurrency_name):
    """concurrency default is to perform updates one machine at a time.

    Concurrency can be:
    - serial: one at a time
    - parallel: all together
    - blue-green: 50% at a time"""

    concurrency_names = ['serial', 'parallel', 'blue-green']

    if concurrency_name == 'blue-green':
        context = context_handler.load_context(stackname)

        if cloudformation.using_elb_v1(stackname):
            return bluegreen.BlueGreenConcurrency(context['aws']['region'])

        return bluegreen_v2.do

    if concurrency_name == 'serial' or concurrency_name == 'parallel':
        return concurrency_name

    if concurrency_name is None:
        return 'parallel'

    raise ValueError("Concurrency %s is not supported. Supported models: %s" % (concurrency_name, concurrency_names))
