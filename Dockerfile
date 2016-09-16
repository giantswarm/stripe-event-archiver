FROM python:2.7-alpine

ENV PYTHONUNBUFFERED True

RUN apk add --update build-base python-dev libffi libffi-dev openssl-dev ca-certificates \
  && pip install cryptography \
  && apk del build-base python-dev libffi-dev openssl-dev \
  && rm -rf /var/cache/apk/*

ADD requirements.txt /
RUN pip install -r /requirements.txt
ADD . /app/

WORKDIR /app

ENTRYPOINT ["python", "/app/main.py"]
