from os.path import join
from StringIO import StringIO
import json, base64
from fabric.api import get
from .config import FabricException

def decode_bvars(contents):
    return json.loads(base64.b64decode(contents))

def encode_bvars(contents):
    return base64.b64encode(json.dumps(contents))

def read_from_current_host():
    "returns the buildvars from the CURRENTLY CONNECTED host"
    # due to a typo we now have two types of file naming in existence
    # prefer hyphenated over underscores
    for fname in ['build-vars.json.b64', 'build_vars.json.b64']:
        try:
            strbuffer = StringIO()
            get(join('/etc/', fname), strbuffer)
            return decode_bvars(strbuffer.getvalue())
        except FabricException:
            # file not found
            continue
