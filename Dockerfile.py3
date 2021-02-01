FROM python:3.6-alpine3.12

# cmake + zlib-dev for parallel-ssh dependencies
# paramiko is pure python and never needed it
RUN apk add --no-cache \
    libressl-dev \
    musl-dev \
    libffi-dev \
    cmake \
    zlib-dev

RUN apk add --no-cache --virtual build-deps \
    curl \
    gcc \
    g++ \
    make

RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python get-pip.py pip && \
    pip install virtualenv && \
    virtualenv --python=python3 /venv && \
    /venv/bin/pip install wheel pip --upgrade
    
COPY requirements.txt /requirements.txt

RUN /venv/bin/pip install -r /requirements.txt

RUN apk del build-deps

CMD /venv/bin/python
