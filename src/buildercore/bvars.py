from io import BytesIO
import json, base64
from .command import get
import logging

LOG = logging.getLogger(__name__)

# json.dumps and json.loads expect ascii unless the json was explicitly encoded as utf8
# which we don't do anywhere in builder.
# <bytes>.decode and <string>.encode() both default to UTF-8
# so we must be careful to preserve the ascii encoding through it's transformations

def decode_bvars(string):
    """decodes a base64 encoded json-serialised string.
    input string can be utf-8 or ascii but output is always ascii"""
    val = base64.b64decode(string).decode('ascii') # bytes => ascii
    return json.loads(val)

def encode_bvars(data):
    "encodes python data to a json-serialised, base64 encoded ascii string"
    val = base64.b64encode(json.dumps(data).encode('ascii'))
    return val.decode('ascii') # bytes => ascii

def read_from_current_host():
    "returns the buildvars from the CURRENTLY CONNECTED host"
    strbuffer = BytesIO()
    get('/etc/build-vars.json.b64', strbuffer)
    return decode_bvars(strbuffer.getvalue())
