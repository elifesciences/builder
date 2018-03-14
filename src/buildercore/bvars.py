from os.path import join
from io import StringIO
import json, base64
from fabric.api import get

def decode_bvars(contents):
    return json.loads(base64.b64decode(contents))

def encode_bvars(contents):
    return base64.b64encode(json.dumps(contents))

def read_from_current_host():
    "returns the buildvars from the CURRENTLY CONNECTED host"
    # due to a typo we now have two types of file naming in existence
    # prefer hyphenated over underscores
    fname = 'build-vars.json.b64'
    strbuffer = StringIO()
    get(join('/etc/', fname), strbuffer)
    return decode_bvars(strbuffer.getvalue())
