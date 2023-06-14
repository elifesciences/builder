FROM python:3.8-alpine3.12

# cmake + zlib-dev for parallel-ssh dependencies
# paramiko is pure python and never needed it
RUN apk add --no-cache \
    cmake \
    git \
    libffi-dev \
    libressl-dev \
    musl-dev \
    zlib-dev

RUN apk add --no-cache --virtual build-deps \
    curl \
    gcc \
    g++ \
    make

RUN python3 -m venv /venv && \
    /venv/bin/pip install wheel pip --upgrade

COPY requirements.txt /requirements.txt

RUN /venv/bin/pip install -r /requirements.txt

RUN apk del build-deps

CMD /venv/bin/python
