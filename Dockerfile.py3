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

# setuptools>=58 dropped support for a dependency 2to3 Troposphere 2.7.1 depends on
RUN python3 -m venv /venv && \
    /venv/bin/pip install wheel pip "setuptools<58" --upgrade

COPY requirements.txt /requirements.txt

RUN /venv/bin/pip install -r /requirements.txt

RUN apk del build-deps

CMD /venv/bin/python
