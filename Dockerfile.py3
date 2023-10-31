FROM python:3.8-slim-bullseye

RUN python3 -m venv /venv && /venv/bin/pip install pip wheel --upgrade

COPY requirements.txt /requirements.txt

RUN /venv/bin/pip install -r /requirements.txt

CMD /venv/bin/python
