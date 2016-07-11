FROM python:2.7-alpine

ENV PYTHONUNBUFFERED True

RUN apk add --update py-pip build-base python-dev \
  && pip install pycrypto \
  && apk del build-base python-dev \
  && rm -rf /var/cache/apk/*

ADD requirements.txt /
RUN pip install -r /requirements.txt
ADD . /app/

ENTRYPOINT ["python", "/app/main.py"]
