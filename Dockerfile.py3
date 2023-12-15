FROM python:3.8-slim-bullseye

# 'git' for installing python dependencies from git revisions
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y git --no-install-recommends

RUN python3 -m venv /venv && /venv/bin/pip install pip wheel --upgrade

COPY requirements.txt /requirements.txt

RUN /venv/bin/pip install -r /requirements.txt

CMD /venv/bin/python
