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

The rest of the configuration variables explained:

- `REDIS_HOST`: hostname or IP address of the redis server. If not given, "redis" will be used.
- `REDIS_PORT`: Port number of the redis server. If not set, 6379 will be used.
- `REDIS_RETENTION_DAYS`: Expiry for keys in redis. 60 is the default here.
- `S3_ENDPOINT`: AWS S3 endpoint to use
- `S3_BUCKET`: Name of the S3 bucket to use
- `S3_PATH`: Path to use within the S3 bucket. Can contain date-specific placeholders like `%Y`, `%m` and `%d`, which will be expanded with the respective values for the daily file.

## File Encryption

We are using an asymmetric encryption/decryption mechanism. The backup service only has knowledge of the public key for encrypting files. The private key required for decrypting files will be kept secret.

## Decrypting Files

See [`utils/`](utils/).

## Key Generation

The encryption mechanism relies on an RSA public/private key pair.
This key pair can be generated using the `ssh-keygen` command line utility.
The key has to be of type `RSA` and has to be stored as PEM file (which is the default setting of `ssh-keygen` these days).
Another setting you have influence on is the key size, which directly influences the strength of the encryption.
A size of `4096` bit is recommended here.

As a first step, generate a private key PEM file:

```nohighlight
ssh-keygen -t rsa -b 4096 -f ./private_key.pem
```

You'll be asked for a password twice. Take note of this password, as you will need it in the future for decrypting backup files.

Then you can create the public key PEM file from the new key like this:

```nohighlight
ssh-keygen -e -m PEM -f ./private_key.pem > ./public_key.pem
```

## Building a Docker Image

We run the archiver service in a Docker container.

For the service to be able to encrypt the backup files, the `public_key.pem` (see [Key Generation](#key-generation) above) file needs to be placed right in the root folder of this repository, so that it gets copied into the Docker image.

To build the image, either use `make` or the long form:

```nohighlight
docker build -t stripe-event-archiver:latest .
```

You are of course free to name and tag the image however you like. If you change the name/tag, remember to update the `docker-compose.yml` in case you want to use that for a local test run. Which is highly recommended.

## Test Run

Once you have updated your `docker-compose.yml` and/or set local environment variables, fire it up!

```
docker-compose up
```

