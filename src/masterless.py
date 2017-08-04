
@requires_project
def launch(pname, instance_id):
    try:
        stackname = generate_stack_from_input(pname, instance_id)
        pdata = core.project_data_for_stackname(stackname)

        print 'attempting to create stack:'
        print '  stackname: ' + stackname
        print '  region:    ' + pdata['aws']['region']
        print

        bootstrap.create_update(stackname)
        setdefault('.active-stack', stackname)
    except core.NoMasterException as e:
        LOG.warn(e.message)
        print "\n%s\ntry `./bldr master.create`'" % e.message


def update():
    pass

def destroy():
    pass
