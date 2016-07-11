# Stripe Event Archiver

Stripe stores events for 30 days only. To be able to trace back transactions over a longer time period, it's necessary to archive these events while they are there.

This services creates daily encrypted backup files and stores them on Amazon AWS S3.

## How It Works

The goal is to make the archiver as robust and idempotent as possible.
The priority is to make sure each and every event lands in an archive file.

- Every day, fetch all the events that are available at Stripe (except for today's events)
- Group the events by their day of creation
- Count the number of events available per day
- Compare the amout of events to the amount previously seen for that same day
- If the number is greater than what's been there before or the day hasn't been treated before:
  - create a backup file for the events of this day
  - encrypt the file
  - upload the encrypted file to S3

The current day, which is the day of the backup run, is ommitted when creating backups. This ensures that in general only one file per day is written. Read on to find out why there might be multiple files for the same day.

The service keeps it's state, which is the number of events handled for a specific day, to avoid creating identical backups for the same day over and over again. redis is used as a storage backend for the state. Losing the state isn't considered critical, as it only means that backups for up to 30 days (or rather 29) days will be created again and overwritten at upload.

Backup files use the [JSON lines](http://jsonlines.org/) format, which is one JSON object per line in an UTF-8 encoded text file. The files are gzipped, indicated by the file ending `.gz`.

Filenames are created from the date the events have been created on (`YYYY-MM-DD`) and a (partial) content hash. This hash represents the exact unencrypted content of a file. Backup files for the same day but with different hashes have different content. In order to get all events archived for a day, all files written for a day need to be handled and possibly merged.

The archived JSON objects have sorted keys. This means that objects with identical data also have an identical text representation. This facilitates removing redundant entries after merging multiple files with simple tools like `sort`.

## Usage

This service is supposed to be running as a Docker container, connected to a redis server.

For local testing with `docker-compose` a `docker-compose.yml.example` file is provided. Copy this to `docker-compose.yml` and edit according to your needs. The file shows which environment variables can be set to configure the service.

The following keys are left empty in the example, which means that you either have to add the values to the file, or make the values available as environment variables when running `docker-compose`.

- `STRIPE_API_KEY`: Your API key for Stripe
- `AWS_ACCESS_KEY_ID`: The ID of an AWS identity
- `AWS_SECRET_ACCESS_KEY`: The secret key for the identity above
- `FILE_ENCRYPTION_PASSWORD`: Passphrase for encryption of the archive files

The rest of the configuration variables explained:

- `REDIS_HOST`: hostname or IP address of the redis server. If not given, "redis" will be used.
- `REDIS_PORT`: Port number of the redis server. If not set, 6379 will be used.
- `REDIS_RETENTION_DAYS`: Expiry for keys in redis. 60 is the default here.
- `S3_ENDPOINT`: AWS S3 endpoint to use
- `S3_BUCKET`: Name of the S3 bucket to use
- `S3_PATH`: Path to use within the S3 bucket. Can contain date-specific placeholders like `%Y`, `%m` and `%d`, which will be expanded with the respective values for the daily file.

## File Encryption

The backup files are encrypted using the AES cypher algorithm in CBC mode with 256 bit (32 Byte) block size. The encryption key is generated from the `FILE_ENCRYPTION_PASSWORD`, just like `openssl` does when using the `-pass` argument (together with the default `-md md5` for MD5 message digest and `-salt` for applying a random salt to the key).

## Decrypting Files

The files can be decrypted using the `openssl` command line utility. With a backup file called `in.jsonl.aes-256-cbc` in your current directory, use the following command to extract the unencrypted JSON lines data.

This requires the encryption password in the environment variable named `FILE_ENCRYPTION_PASSWORD`.

```nohighlight
openssl aes-256-cbc -d -a -pass env:FILE_ENCRYPTION_PASSWORD -in in.jsonl.aes-256-cbc -out out.jsonl
```

## Acknowledgements

Thanks to [Joe Linoff](http://joelinoff.com/blog/?p=885) for providing code to create openssl-friendly data encryption in Python (contained as `mycrypt.py` and licensed under MIT-like terms).
