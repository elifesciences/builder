from os.path import join
from io import BytesIO
import json, base64
from fabric.api import get

def decode_bvars(contents):
    return json.loads(base64.b64decode(contents).decode())

def encode_bvars(data):
    return base64.b64encode(json.dumps(data).encode())

def read_from_current_host():
    "returns the buildvars from the CURRENTLY CONNECTED host"
    strbuffer = BytesIO()
    get('/etc/build-vars.json.b64', strbuffer)
    return decode_bvars(strbuffer.getvalue())
