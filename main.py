
from datetime import datetime
from datetime import timedelta
from redis import StrictRedis
from requests.auth import HTTPBasicAuth
from subprocess import call
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
            dt = datetime.strptime(daystring, "%Y-%m-%d")

            filename = dump_to_file(daystring, events[daystring])
            target_path = ""
            if S3_PATH is not None:
                target_path = dt.strftime(S3_PATH)
            target_path += "/" + filename
            upload_backup(s3, filename, target_path)
            os.remove(filename)

            # write number of entries per day to redis
            redis.setex(daystring, redis_retention, str(len(events[daystring])))
        except Exception as ex:
            sys.stderr.write("ERROR: No backup created for %s\n" % daystring)
            sys.stderr.write(traceback.format_exc() + "\n")

    del redis
    del s3
    del events

    print("Done for today.")


def fetch_events():
    has_more = True
    params = {"limit": 100}
    auth = HTTPBasicAuth(STRIPE_API_KEY, '')
    while has_more:
        r = requests.get("https://api.stripe.com/v1/events",
                         params=params,
                         auth=auth)
        r.raise_for_status()
        j = r.json()
        has_more = j["has_more"]
        params["starting_after"] = j["data"][-1]["id"]
        for item in j["data"]:
            yield item


def dump_to_file(daystring, events):
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
    filename = daystring + "_" + sha1hash[0:6] + ".jsonl"

    # write to file
    with open(filename, 'wb') as dumpfile:
        print("%s: Dumping to file %s" % (daystring, filename))
        dumpfile.write(dump)
    del dump

    # encrypt file
    new_filename = filename + ".aes-256-cbc"
    call(["openssl", "enc", "-aes-256-cbc", "-base64",
          "-pass", "env:FILE_ENCRYPTION_PASSWORD",
          "-in", filename, "-out", new_filename])
    os.remove(filename)

    return new_filename


def upload_backup(s3conn, local_path, target_path):
    """
    Uploads a backup file to S3
    """
    with open(local_path, "rb") as file_pointer:
        s3conn.upload(target_path, file_pointer)


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

    while True:
        archive_events()

        # Wait for a day
        time.sleep(60 * 60 * 24)
