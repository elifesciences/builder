FROM python:3.5-slim-jessie

RUN pip install virtualenv
RUN mkdir /venv && virtualenv --python=python3 /venv
COPY requirements.txt /requirements.txt
COPY settings.yml /settings.yml
RUN /venv/bin/pip install -r /requirements.txt
CMD /venv/bin/python
