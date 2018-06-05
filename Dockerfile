FROM python:2.7.15-slim-stretch

RUN pip install virtualenv
RUN mkdir /venv && virtualenv --python=python2 /venv
COPY py2-requirements.txt /
RUN /venv/bin/pip install -r /py2-requirements.txt
CMD /venv/bin/python
