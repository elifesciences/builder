FROM python:3.5-alpine3.8

# cmake + zlib-dev for parallel-ssh dependencies
# paramiko is pure python and never needed it
RUN apk add --no-cache \
    libressl-dev \
    musl-dev \
    libffi-dev \
    cmake \
    zlib-dev

COPY requirements.txt /requirements.txt

RUN apk add --no-cache --virtual build-deps \
    curl \
    gcc \
    make \
    && \
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python get-pip.py pip==9.0.2 && \
    pip install virtualenv && \
    mkdir /venv && \
    virtualenv --python=python3 /venv && \
    /venv/bin/pip install -r /requirements.txt && \
    apk del build-deps

CMD /venv/bin/python
