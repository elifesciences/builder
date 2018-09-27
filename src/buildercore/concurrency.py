from . import bluegreen, context_handler

# TODO: move as buildercore.concurrency.concurrency_for
def concurrency_for(stackname, concurrency_name):
    """concurrency default is to perform updates one machine at a time.

    Concurrency can be:
    - serial: one at a time
    - parallel: all together
    - blue-green: 50% at a time"""

    if concurrency_name == 'blue-green':
        context = context_handler.load_context(stackname)
        return bluegreen.BlueGreenConcurrency(context['aws']['region'])
    if concurrency_name == 'serial' or concurrency_name == 'parallel':
        # maybe return a fabric object in the future
        return concurrency_name

    if concurrency_name is None:
        return 'parallel'

    raise ValueError("Concurrency %s is not supported" % concurrency_name)
