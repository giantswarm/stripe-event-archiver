# Decrypting Files

To decrypt an encrypted backup file, you need:

- the private key PEM file
- the password for that key
- the utility `decrypt.py` provided in `utils/`

Before using `decrypt.py`, make sure you have the dependencies installed on your local system by running

```nohighlight
cd utils
pip install -r requirements.txt
```

Depending on the system you use, this might require some additional libraries. As a guideline, here is what is required on a bare-bones Alpine 3.4 Linux:

```nohighlight
apk add --update build-base python-dev libffi libffi-dev openssl-dev ca-certificates
```

On Mac OS X, beware when you used `homebrew` to install your `openssl`. In this case, try installing the dependencies this way:

```nohighlight
LDFLAGS="-L/usr/local/opt/openssl/lib" pip install cryptography --no-use-wheel
```

Now let's decrypt an encrypted backup file:


```nohighlight
python decrypt.py --key ./private_key.pem 2016-07-07_d52ab54f.jsonl.enc
```

You'll get asked for the password of the private key. After decryption is complete, a new file `2016-07-07_d52ab54f.jsonl` is present in the same directory that contains the source file.

Instead of a single source file, you can provide a pattern, like `*` or `2016-09*` to decrypt multiple files in one run.
