# coding: utf8

from base64 import b64decode
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from getpass import getpass
import argparse
import glob
import os
import sys


def read_key(path, password):
    with open(path, "r") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=password,
            backend=default_backend()
        )
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError("Unexpectd key format: %s" % type(private_key))
        return private_key


def decrypt_file(private_key, path):
    with open(path, "r") as inputfile:
        encrypted = inputfile.read()
        encrypted_chunks = encrypted.strip().split("\n")
        decrypted = ""
        for chunk in encrypted_chunks:
            chunk = b64decode(chunk)
            decrypted_chunk = private_key.decrypt(
                chunk,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA1()),
                    algorithm=hashes.SHA1(),
                    label=None
                )
            )
            decrypted += decrypted_chunk
        decrypted = b64decode(decrypted)
        return decrypted


def cli():
    parser = argparse.ArgumentParser(description='Decrypt files created by stripe-event-archiver')
    parser.add_argument('input_files', metavar='FILES', type=str, help='Path or path pattern of the encrypted file(s)')
    parser.add_argument('-k', '--key', dest='key', help='Path of the private key file in PEM format')
    parser.add_argument('-p', '--pass', dest='passphrase', help='Passphrase for the key. If not given, will be prompted.')
    args = parser.parse_args()

    if args.key is None:
        sys.stderr.write("Please provide a key path using the -k/--key argument.\n")
        sys.exit(1)

    files = glob.glob(args.input_files)
    if len(files) == 0:
        sys.stderr.write("ERROR: No input files found.\n")
        sys.exit(2)

    if args.passphrase is None:
        passphrase = getpass('Passphrase for key %s: ' % args.key)
    else:
        passphrase = args.passphrase

    key = read_key(args.key, passphrase)

    for f in files:
        if f[-10:] == ".jsonl.enc":
            new_filename = f[0:-4]
            if os.path.exists(new_filename):
                sys.stderr.write("ERROR: File %s already exists. Not overwritten.\n" % new_filename)
            else:
                try:
                    plain = decrypt_file(key, f)
                    with open(new_filename, "w") as outfile:
                        outfile.write(plain)
                        print("Decrypting %s to %s" % (f, new_filename))
                        del plain
                except ValueError as e:
                    sys.stderr.write("ERROR: File %s cannot be decrypted.\n" % f)
                    sys.stderr.write("Details: %s.\n" % e)


if __name__ == "__main__":
    cli()
