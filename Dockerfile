FROM python:2.7-alpine

ENV PYTHONUNBUFFERED True

# Here we install pycrypto
RUN apk add --update openssl \
  && rm -rf /var/cache/apk/*

# Installing further dependencies that need no compilation
ADD requirements.txt /
RUN pip install -r /requirements.txt
ADD . /app/

ENTRYPOINT ["python", "/app/main.py"]
