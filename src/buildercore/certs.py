# pylint: disable=no-member
import ssl, socket
from dateutil.parser import parse
from . import utils, project, core

import logging
LOG = logging.getLogger(__name__)

def cert_info(hostname, verbose=False):
    # http://stackoverflow.com/questions/30862099/how-can-i-get-certificate-issuer-information-in-python
    ret = {'hostname': hostname,
           'results': {}}
    if not hostname:
        ret['results'] = "HOVERBOARDS DON'T WORK ON WATER."
        return ret
    timeout = 1 # seconds
    try:
        LOG.info("fetching certificate info for %r", hostname)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = ctx.wrap_socket(socket.socket(), server_hostname=hostname)
        sock.settimeout(timeout)
        sock.connect((hostname, 443))
        cert = sock.getpeercert()
        LOG.debug("got: %r", cert)
        if not cert:
            ret['results'] = 'no results'
            return ret

        now = utils.utcnow()
        subject = dict(x[0] for x in cert['subject'])
        issuer = dict(x[0] for x in cert['issuer'])
        starts = parse(cert['notBefore'])
        ends = parse(cert['notAfter'])
        struct = {
            'issued_to': subject['commonName'],
            'issued_by': issuer['commonName'],

            'starts': starts,
            'starts_offset': (now - starts).days,        
            'ends': ends,
            'ends_offset': (ends - now).days,
        }
        if verbose:
            struct['raw'] = cert

        ret['results'] = struct
        return ret

    except socket.timeout as err:
        LOG.error("failed to fetch certificate, connection timed out after %s seconds", timeout)
        ret['results'] = 'timed out'

    except socket.error:
        LOG.error("failed to fetch certificate, connection was refused. possibly no SSL configured")
        ret['results'] = 'refused'
        
    except ssl.SSLError as err:
        LOG.error("failed to fetch certificate for %r", hostname)
        ret['results'] = err.reason
    
    except:
        LOG.exception("unhandled exception attempting to fetch certificate for hostname %r", hostname)
        raise

    return ret

def stack_certificate(stackname):
    "returns certificate information for given stackname"
    results = cert_info(core.hostname_struct(stackname).get('full_hostname'))
    results['stackname'] = stackname
    return results

def project_certificates(pname):
    "returns certificate information for all active instances of a given project"
    pdata = project.project_data(pname)
    subdomain = pdata.get('subdomain')
    if subdomain:
        project_stacks = core.stack_names(core.active_aws_project_stacks(pname))
        return map(stack_certificate, project_stacks)
    return []

def all_certificates(region=None):
    "returns certificate information for all active instances of all projects"
    region = region or core.find_region()
    return map(stack_certificate, core.active_stack_names(region))

def certificate_report(region=None):
    certs = all_certificates(region)
    dump = utils.json_dumps(certs, dangerous=True)
    open('/tmp/certs.report', 'w').write(dump)
