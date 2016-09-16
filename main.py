from base64 import b64encode
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from datetime import datetime
from datetime import timedelta
from redis import StrictRedis
from requests.auth import HTTPBasicAuth
from StringIO import StringIO
from subprocess import call
import backoff
import hashlib
import json
import os
import requests
import sys
import time
import tinys3
import traceback


# Some configuration from environment variables
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_RETENTION_DAYS = int(os.getenv("REDIS_RETENTION_DAYS", "30"))
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PATH = os.getenv("S3_PATH")

PUBLIC_KEY = None

def archive_events():
    print("Starting to archive events.")
    redis = StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    s3 = tinys3.Connection(AWS_ACCESS_KEY_ID,
                           AWS_SECRET_ACCESS_KEY,
                           default_bucket=S3_BUCKET,
                           endpoint=S3_ENDPOINT,
                           tls=True)

    now = datetime.utcnow()
    nowstring = now.strftime("%Y-%m-%d")

    # 1. We collect all events objects from the query time span
    # and group them by day.

    # keep everything in RAM, keyed by day
    events = {}
    count = 0
    for event in fetch_events():
        event_datetime = datetime.fromtimestamp(event["created"])
        daystring = event_datetime.strftime("%Y-%m-%d")
        if daystring == nowstring:
            continue
        if daystring not in events:
            events[daystring] = []
        count += 1
        events[daystring].append(event)
    print("Fetched %d events." % count)

    # 2. We go through day by day and see where new entries have been added
    # since the last run. For these we create a backup file.

    redis_retention = REDIS_RETENTION_DAYS * 24 * 60 * 60

    for daystring in sorted(events.keys()):
        print("Processing day %s with %d events" % (daystring, len(events[daystring])))

        # possibly skip days already archived
        redis_value = redis.get(daystring)
        if redis_value is not None:
            num_entries_before = int(redis_value)
            if len(events[daystring]) <= num_entries_before:
                print("Skipping day %s, already archived" % daystring)
                continue

        try:
            target_path = upload_dump(daystring, events[daystring], s3)
            print("Uploaded %s" % target_path)
            # write number of entries per day to redis
            redis.setex(daystring, redis_retention, str(len(events[daystring])))
        except Exception as ex:
            sys.stderr.write("ERROR: No backup created for %s\n" % daystring)
            sys.stderr.write(traceback.format_exc() + "\n")

    del redis
    del s3
    del events

    print("Done for today.")


@backoff.on_exception(backoff.expo,
                      requests.exceptions.ConnectionError,
                      max_tries=8)
def fetch_events():
    has_more = True
    params = {"limit": 100}
    auth = HTTPBasicAuth(STRIPE_API_KEY, '')
    while has_more:
        r = requests.get("https://api.stripe.com/v1/events",
                         params=params,
                         auth=auth)
        j = r.json()
        has_more = j["has_more"]
        params["starting_after"] = j["data"][-1]["id"]
        for item in j["data"]:
            yield item


def upload_dump(daystring, events, s3conn):
    """
    Creates a backup file from a list of events
    """
    dump = ""
    hasher = hashlib.sha1()
    for item in events:
        j = json.dumps(item, sort_keys=True) + "\n"
        hasher.update(j)
        dump += j
    sha1hash = hasher.hexdigest()
    filename = daystring + "_" + sha1hash[0:6] + ".jsonl.enc"

    # encrypt to string buffer
    encrypted = encrypt(dump, PUBLIC_KEY)
    del dump
    output = StringIO(encrypted)
    del encrypted
    output.seek(0)

    target_path = ""
    if S3_PATH is not None:
        dt = datetime.strptime(daystring, "%Y-%m-%d")
        target_path = dt.strftime(S3_PATH)
    target_path += "/" + filename
    s3conn.upload(target_path, output)
    output.close()

    return target_path


def encrypt(string, public_key):
    # First we encode the string into one long line
    # of base64 data, then chunk according to the key length
    string = b64encode(string)
    chunk_length = (public_key.key_size / 8) - 50
    chunks = [string[i:i+chunk_length] for i in range(0, len(string), chunk_length)]
    del string

    # Now we encrypt chunk by chunk and write back
    # one line per chunk, again base64 encoded
    encrypted_text = ""
    for chunk in chunks:
        encrypted_chunk = public_key.encrypt(
            chunk,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None
            )
        )
        encrypted_chunk = b64encode(encrypted_chunk)
        encrypted_text += encrypted_chunk + "\n"

    return encrypted_text


def read_key(pem_path):
    with open(pem_path, "r") as public_pem_file:
        public_pem_data = public_pem_file.read()
        public_key = load_pem_public_key(public_pem_data, backend=default_backend())

    if not isinstance(public_key, rsa.RSAPublicKey):
        raise Exception("Unexpectd key format: %s" % type(public_key))
    return public_key


if __name__ == "__main__":

    # check for the existence of environment variables
    required_env_vars = ["STRIPE_API_KEY", "AWS_ACCESS_KEY_ID",
                     "AWS_SECRET_ACCESS_KEY", "S3_ENDPOINT",
                     "S3_BUCKET"]
    missing_env_vars = []
    for v in required_env_vars:
        val = os.getenv(v)
        if val is None or val == "":
            missing_env_vars.append(v)
    if len(missing_env_vars):
        sys.stderr.write("One or more required environment variables are missing: ")
        sys.stderr.write(", ".join(missing_env_vars) + "\n")
        sys.exit(1)

    PUBLIC_KEY = read_key("./public_key.pem")

    while True:
        archive_events()

        # Wait for a day
        time.sleep(60 * 60 * 24)
