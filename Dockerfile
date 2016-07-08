FROM python:2.7-alpine

ENV PYTHONUNBUFFERED True

RUN apk add --update openssl \
  && rm -rf /var/cache/apk/*

ADD requirements.txt /
RUN pip install -r /requirements.txt
ADD . /app/

ENTRYPOINT ["python", "/app/main.py"]
