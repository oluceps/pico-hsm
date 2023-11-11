#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
/*
 * This file is part of the Pico HSM distribution (https://github.com/polhenarejos/pico-hsm).
 * Copyright (c) 2022 Pol Henarejos.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */
"""

import sys
try:
    from cvc.certificates import CVC
    from cvc.oid import oid2scheme
    from cvc.utils import scheme_rsa
except ModuleNotFoundError:
    print('ERROR: cvc module not found! Install pycvc package.\nTry with `pip install pycvc`')
    sys.exit(-1)

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives import hashes
except ModuleNotFoundError:
    print('ERROR: cryptography module not found! Install cryptography package.\nTry with `pip install cryptography`')
    sys.exit(-1)

try:
    from picohsm import PicoHSM, PinType, DOPrefixes, KeyType, EncryptionMode, utils, APDUResponse, SWCodes
except ModuleNotFoundError:
    print('ERROR: picohsm module not found! Install picohsm package.\nTry with `pip install pypicohsm`')
    sys.exit(-1)

import json
import urllib.request
import base64
from binascii import hexlify, unhexlify
import sys
import argparse
import os
import platform
from datetime import datetime
from argparse import RawTextHelpFormatter

pin = None

def hexy(a):
    return [hex(i) for i in a]

def parse_args():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(title="commands", dest="command")
    parser_init = subparser.add_parser('initialize', help='Performs the first initialization of the Pico HSM.')
    parser.add_argument('--pin', help='PIN number')
    parser_init.add_argument('--so-pin', help='SO-PIN number')
    parser_init.add_argument('--silent', help='Confirms initialization silently.', action='store_true')

    parser_attestate = subparser.add_parser('attestate', help='Generates an attestation report for a private key and verifies the private key was generated in the devices or outside.')
    parser_attestate.add_argument('-k', '--key', help='The private key index', metavar='KEY_ID')

    parser_pki = subparser.add_parser('pki', help='Performs PKI operations.')
    subparser_pki = parser_pki.add_subparsers(title='commands', dest='subcommand')
    parser_pki_init = subparser_pki.add_parser('initialize', help='Initializes the Public Key Infrastructure (PKI)')

    parser_pki_init.add_argument('--certs-dir', help='Store the PKI certificates into this directory.', default='certs')
    parser_pki_init.add_argument('--default', help='Setups the default public PKI from public Pico HSM PKI.', action='store_true')
    parser_pki_init.add_argument('--force', help='Forces the download of certificates.', action='store_true')

    parser_rtc = subparser.add_parser('datetime', help='Datetime operations with the integrated Real Time Clock (RTC).')
    subparser_rtc = parser_rtc.add_subparsers(title='commands', dest='subcommand')
    parser_rtc_set = subparser_rtc.add_parser('set', help='Sets the current datetime.')
    parser_rtc_get = subparser_rtc.add_parser('get', help='Gets the current datetime.')

    parser_opts = subparser.add_parser('options', help='Manage extra options.', formatter_class=RawTextHelpFormatter)
    subparser_opts = parser_opts.add_subparsers(title='commands', dest='subcommand')
    parser_opts_set = subparser_opts.add_parser('set', help='Sets option OPT.')
    parser_opts_get = subparser_opts.add_parser('get', help='Gets optiont OPT.')
    parser_opts.add_argument('opt', choices=['button', 'counter'], help='button: press-to-confirm button.\ncounter: every generated key has an internal counter.', metavar='OPT')
    parser_opts_set.add_argument('onoff', choices=['on', 'off'], help='Toggles state ON or OFF', metavar='ON/OFF', nargs='?')

    parser_secure = subparser.add_parser('secure', help='Manages security of Pico HSM.')
    subparser_secure = parser_secure.add_subparsers(title='commands', dest='subcommand')
    parser_opts_enable = subparser_secure.add_parser('enable', help='Enables secure lock.')
    parser_opts_unlock = subparser_secure.add_parser('unlock', help='Unlocks the secure lock.')
    parser_opts_disable = subparser_secure.add_parser('disable', help='Disables secure lock.')

    parser_cipher = subparser.add_parser('cipher', help='Implements extended symmetric ciphering with new algorithms and options.\n\tIf no file input/output is specified, stdin/stdout will be used.')
    subparser_cipher = parser_cipher.add_subparsers(title='commands', dest='subcommand')
    parser_cipher_encrypt = subparser_cipher.add_parser('encrypt', help='Performs encryption.')
    parser_cipher_decrypt = subparser_cipher.add_parser('decrypt', help='Performs decryption.')
    parser_cipher_keygen = subparser_cipher.add_parser('keygen', help='Generates new AES key.')
    parser_cipher_hmac = subparser_cipher.add_parser('mac', help='Computes MAC (HMAC or CMAC).')
    parser_cipher_kdf = subparser_cipher.add_parser('kdf', help='Performs key derivation function on a secret key.')
    parser_cipher_encrypt.add_argument('--alg', choices=['CHACHAPOLY'], required=True)
    parser_cipher_decrypt.add_argument('--alg', choices=['CHACHAPOLY'], required=True)

    parser_cipher_hmac.add_argument('--alg', choices=['CMAC', 'HMAC-SHA1', 'HMAC-SHA224', 'HMAC-SHA256', 'HMAC-SHA384', 'HMAC-SHA512'], help='Selects the algorithm.', required=True)
    parser_cipher_kdf.add_argument('--alg', choices=['HKDF-SHA256', 'HKDF-SHA384', 'HKDF-SHA512', 'PBKDF2-SHA1', 'PBKDF2-SHA224', 'PBKDF2-SHA256', 'PBKDF2-SHA384', 'PBKDF2-SHA512', 'X963-SHA1', 'X963-SHA224', 'X963-SHA256', 'X963-SHA384', 'X963-SHA512'], help='Selects the algorithm.', required=True)
    parser_cipher_kdf.add_argument('--output-len', help='Specifies the output length of derived material.')
    parser_cipher_kdf.add_argument('--iteration', help='Iteration count.', required=any(['PBKDF2' in s for s in sys.argv]))

    parser_cipher.add_argument('--iv', help='Sets the IV/nonce (hex string).')
    parser_cipher.add_argument('--file-in', help='File to encrypt or decrypt.')
    parser_cipher.add_argument('--file-out', help='File to write the result.')
    parser_cipher.add_argument('--aad', help='Specifies the authentication data (it can be a string or hex string. Combine with --hex if necesary).')
    parser_cipher.add_argument('--hex', help='Parses the AAD parameter as a hex string (for binary data).', action='store_true')
    parser_cipher.add_argument('-k', '--key', help='The private key index', metavar='KEY_ID', required=True)
    parser_cipher.add_argument('-s', '--key-size', default=32, help='Size of the key in bytes.')

    parser_x25519 = argparse.ArgumentParser(add_help=False)
    subparser_x25519 = parser_x25519.add_subparsers(title='commands', dest='subcommand')
    parser_x25519_keygen = subparser_x25519.add_parser('keygen', help='Generates a keypair for X25519 or X448.')
    parser_x25519.add_argument('-k', '--key', help='The private key index', metavar='KEY_ID', required=True)

    # Subparsers based on parent

    parser_create = subparser.add_parser("x25519", parents=[parser_x25519],
                                        help='X25519 key management.')
    # Add some arguments exclusively for parser_create

    parser_update = subparser.add_parser("x448", parents=[parser_x25519],
                                        help='X448 key management.')
    # Add some arguments exclusively for parser_update

    args = parser.parse_args()
    return args

def get_pki_data(url, data=None, method='GET'):
    user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; '
    'rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'
    method = 'GET'
    if (data is not None):
        method = 'POST'
    req = urllib.request.Request(f"https://www.picokeys.com/pico/pico-hsm/{url}/",
                                method=method,
                                data=data,
                                headers={'User-Agent': user_agent, })
    response = urllib.request.urlopen(req)
    resp = response.read().decode('utf-8')
    j = json.loads(resp)
    return j

def get_pki_certs(certs_dir='certs', force=False):
    certs = get_pki_data('certs')
    if (os.path.exists(certs_dir) is False):
        os.mkdir(certs_dir)
    cvcap = os.path.join(certs_dir, certs['cvca']['CHR'])
    dvcap = os.path.join(certs_dir, certs['dvca']['CHR'])
    if (os.path.exists(cvcap) is False or force is True):
        with open(cvcap, 'wb') as f:
            f.write(base64.urlsafe_b64decode(certs['cvca']['cert']))
    if (os.path.exists(dvcap) is False or force is True):
        with open(dvcap, 'wb') as f:
            f.write(base64.urlsafe_b64decode(certs['dvca']['cert']))
    print(f'All PKI certificates are stored at {certs_dir} folder')

def pki(_, args):
    if (args.subcommand == 'initialize'):
        if (args.default is True):
            get_pki_certs(certs_dir=args.certs_dir, force=args.force)
        else:
            print('Error: no PKI is passed. Use --default to retrieve default PKI.')

def initialize(picohsm, args):
    if (not args.silent):
        print('********************************')
        print('*   PLEASE READ IT CAREFULLY   *')
        print('********************************')
        print('')
        print('This tool will erase and reset your device. It will delete all '
            'private and secret keys.')
        print('Are you sure?')
        _ = input('[Press enter to confirm]')

    if (args.pin):
        try:
            picohsm.login(args.pin)
        except APDUResponse:
            pass
        pin = args.pin
    else:
        pin = '648219'

    if (args.so_pin):
        try:
            picohsm.login(args.so_pin, who=PinType.SO_PIN)
        except APDUResponse:
            pass
        so_pin = args.so_pin
    else:
        so_pin = '57621880'

    picohsm.initialize(pin=pin, sopin=so_pin)
    response = picohsm.get_contents(DOPrefixes.EE_CERTIFICATE_PREFIX, 0x00)

    cert = bytearray(response)
    Y = CVC().decode(cert).pubkey().find(0x86).data()
    print(f'Public Point: {hexlify(Y).decode()}')

    pbk = base64.urlsafe_b64encode(Y)
    data = urllib.parse.urlencode({'pubkey': pbk}).encode()
    j = get_pki_data('cvc', data=data)
    print('Device name: '+j['devname'])
    dataef = base64.urlsafe_b64decode(
        j['cvcert']) + base64.urlsafe_b64decode(j['dvcert']) + base64.urlsafe_b64decode(j['cacert'])

    picohsm.select_file(0x2f02)
    response = picohsm.put_contents(0x0000, data=dataef)

    print('Certificate uploaded successfully!')
    print('')
    print('Note that the device is initialized with a default PIN and '
        'configuration.')
    print('Now you can initialize the device as usual with your chosen PIN '
        'and configuration options.')

def attestate(picohsm, args):
    kid = int(args.key)
    termca = picohsm.get_termca()
    devcert = termca['cv']['data']
    cert = picohsm.get_contents(0xCE, kid)

    print(hexlify(bytearray(cert)))
    print(f'Details of key {kid}:\n')
    print(f'  CAR: {(CVC().decode(cert).car()).decode()}')
    print('  Public Key:')
    puboid = CVC().decode(cert).pubkey().oid()
    print(f'    Scheme: {oid2scheme(puboid)}')
    chr = CVC().decode(cert).chr()
    car = CVC().decode(cert).car()
    if (scheme_rsa(puboid)):
        print(f'    Modulus: {hexlify(CVC().decode(cert).pubkey().find(0x81).data()).decode()}')
        print(f'    Exponent: {hexlify(CVC().decode(cert).pubkey().find(0x82).data()).decode()}')
    else:
        print(f'    Public Point: {hexlify(CVC().decode(cert).pubkey().find(0x86).data()).decode()}')
    print(f'  CHR: {chr.decode()}')
    print('  Key signature:')
    inret = CVC().decode(cert).verify()
    if (inret):
        print('    Status: VALID')
        print(f'      This certificate is signed with private key {kid}')
    else:
        print('    Status: NOT VALID')
        print(f'      This certificate is NOT signed with private key {kid}')
    print('  Cert signature:')
    print(f'    Outer CAR: {CVC().decode(cert).outer_car().decode()}')
    outret = CVC().decode(cert).verify(outer=True, dica=devcert, curve=ec.SECP256R1())
    if (outret):
        print('    Status: VALID')
        print('      This certificate is signed with the device key')
    else:
        print('    Status: NOT VALID')
        print('      This certificate is NOT signed with the device key')

    if (inret is True and outret is True):
        print(f'Key {kid} is generated by device {chr.decode()}')
    else:
        print(f'Key {kid} is NOT generated by device {chr.decode()}')

def rtc(picohsm, args):
    if (args.subcommand == 'set'):
        now = datetime.now()
        _ = picohsm.send(cla=0x80, command=0x64, p1=0x0A, data=list(now.year.to_bytes(2, 'big')) + [now.month, now.day, now.weekday(), now.hour, now.minute, now.second ])
    elif (args.subcommand == 'get'):
        response = picohsm.send(cla=0x80, command=0x64, p1=0x0A)
        dt = datetime(int.from_bytes(response[:2], 'big'), response[2], response[3], response[5], response[6], response[7])
        print(f'Current date and time is: {dt.ctime()}')

def opts(picohsm, args):
    opt = 0x0
    if (args.opt == 'button'):
        opt = 0x1
    elif (args.opt == 'counter'):
        opt = 0x2
    current = picohsm.send(cla=0x80, command=0x64, p1=0x6)[0]
    if (args.subcommand == 'set'):
        if (args.onoff == 'on'):
            newopt = current | opt
        else:
            newopt = current & ~opt
        picohsm.send(cla=0x80, command=0x64, p1=0x6, data=[newopt])
    elif (args.subcommand == 'get'):
        print(f'Option {args.opt.upper()} is {"ON" if current & opt else "OFF"}')

class SecureLock:
    def __init__(self, picohsm):
        self.picohsm = picohsm

    def mse(self):
        sk = ec.generate_private_key(ec.SECP256R1())
        pn = sk.public_key().public_numbers()
        self.__pb = sk.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

        ret = self.picohsm.send(cla=0x80, command=0x64, p1=0x3A, p2=0x01, data=list(self.__pb))

        pk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes(ret))
        shared_key = sk.exchange(ec.ECDH(), pk)

        xkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=12+32,
            salt=None,
            info=self.__pb
        )
        kdf_out = xkdf.derive(shared_key)
        self.__key_enc = kdf_out[12:]
        self.__iv = kdf_out[:12]

    def encrypt_chacha(self, data):
        chacha = ChaCha20Poly1305(self.__key_enc)
        ct = chacha.encrypt(self.__iv, data, self.__pb)
        return ct

    def unlock_device(self):
        ct = self.get_skey()
        self.picohsm.send(cla=0x80, command=0x64, p1=0x3A, p2=0x03, data=list(ct))

    def _get_key_device(self):
        if (platform.system() == 'Windows' or platform.system() == 'Linux'):
            from secure_key import windows as skey
        elif (platform.system() == 'Darwin'):
            from secure_key import macos as skey
        else:
            print('ERROR: platform not supported')
            sys.exit(-1)
        return skey.get_secure_key()

    def get_skey(self):
        self.mse()
        ct = self.encrypt_chacha(self._get_key_device())
        return ct

    def enable_device_aut(self):
        ct = self.get_skey()
        self.picohsm.send(cla=0x80, command=0x64, p1=0x3A, p2=0x02, data=list(ct))

    def disable_device_aut(self):
        ct = self.get_skey()
        self.picohsm.send(cla=0x80, command=0x64, p1=0x3A, p2=0x04, p3=list(ct))

def secure(picohsm, args):
    slck = SecureLock(picohsm)
    if (args.subcommand == 'enable'):
        slck.enable_device_aut()
    elif (args.subcommand == 'unlock'):
        slck.unlock_device()
    elif (args.subcommand == 'disable'):
        slck.disable_device_aut()

def cipher(picohsm, args):
    if (args.subcommand == 'keygen'):
        ret = picohsm.key_generation(KeyType.AES, param=args.key_size * 8)
    else:
        if (args.file_in):
            fin = open(args.file_in, 'rb')
        else:
            fin = sys.stdin.buffer
        enc = fin.read()
        fin.close()
        iv = args.iv
        if (args.iv and args.hex):
            iv = unhexlify(iv)
        aad = args.aad
        if (args.aad and args.hex):
                aad = unhexlify(aad)

        mode = EncryptionMode.ENCRYPT if args.subcommand[0] == 'e' else EncryptionMode.DECRYPT
        if (args.alg == 'CHACHAPOLY'):
            ret = picohsm.chachapoly(args.key, mode, data=enc, iv=iv, aad=aad)
        elif (args.alg == 'CMAC'):
            ret = picohsm.cmac(keyid=args.key, data=enc)
        elif (args.alg == 'HMAC-SHA1'):
            ret = picohsm.hmac(hashes.SHA1, args.key, data=enc)
        elif (args.alg == 'HMAC-SHA224'):
            ret = picohsm.hmac(hashes.SHA224, args.key, data=enc)
        elif (args.alg == 'HMAC-SHA256'):
            ret = picohsm.hmac(hashes.SHA256, args.key, data=enc)
        elif (args.alg == 'HMAC-SHA384'):
            ret = picohsm.hmac(hashes.SHA384, args.key, data=enc)
        elif (args.alg == 'HMAC-SHA512'):
            ret = picohsm.hmac(hashes.SHA512, args.key, data=enc)
        elif (args.alg == 'HKDF-SHA256'):
            ret = picohsm.hkdf(hashes.SHA256, args.key, data=enc, salt=iv, out_len=args.output_len)
        elif (args.alg == 'HKDF-SHA384'):
            ret = picohsm.hkdf(hashes.SHA384, args.key, data=enc, salt=iv, out_len=args.output_len)
        elif (args.alg == 'HKDF-SHA512'):
            ret = picohsm.hkdf(hashes.SHA512, args.key, data=enc, salt=iv, out_len=args.output_len)
        elif (args.alg == 'PBKDF2-SHA1'):
            ret = picohsm.pbkdf2(hashes.SHA1, args.key, salt=iv, iterations=args.iteration, out_len=args.output_len)
        elif (args.alg == 'PBKDF2-SHA224'):
            ret = picohsm.pbkdf2(hashes.SHA224, args.key, salt=iv, iterations=args.iteration, out_len=args.output_len)
        elif (args.alg == 'PBKDF2-SHA256'):
            ret = picohsm.pbkdf2(hashes.SHA256, args.key, salt=iv, iterations=args.iteration, out_len=args.output_len)
        elif (args.alg == 'PBKDF2-SHA384'):
            ret = picohsm.pbkdf2(hashes.SHA384, args.key, salt=iv, iterations=args.iteration, out_len=args.output_len)
        elif (args.alg == 'PBKDF2-SHA512'):
            ret = picohsm.pbkdf2(hashes.SHA512, args.key, salt=iv, iterations=args.iteration, out_len=args.output_len)
        elif (args.alg == 'X963-SHA1'):
            ret = picohsm.x963(hashes.SHA1, args.key, data=enc, out_len=args.output_len)
        elif (args.alg == 'X963-SHA224'):
            ret = picohsm.x963(hashes.SHA224, args.key, data=enc, out_len=args.output_len)
        elif (args.alg == 'X963-SHA256'):
            ret = picohsm.x963(hashes.SHA256, args.key, data=enc, out_len=args.output_len)
        elif (args.alg == 'X963-SHA384'):
            ret = picohsm.x963(hashes.SHA384, args.key, data=enc, out_len=args.output_len)
        elif (args.alg == 'X963-SHA512'):
            ret = picohsm.x963(hashes.SHA512, args.key, data=enc, out_len=args.output_len)

        if (args.file_out):
            fout = open(args.file_out, 'wb')
        else:
            fout = sys.stdout.buffer
        if (args.hex):
            fout.write(hexlify(bytes(ret)))
        else:
            fout.write(bytes(ret))
        if (args.file_out):
            fout.close()

def x25519(picohsm, args):
    if (args.command == 'x25519'):
        P = b'\x7f\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xed'
        A = utils.int_to_bytes(0x01DB42)
        N = b'\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x14\xDE\xF9\xDE\xA2\xF7\x9C\xD6\x58\x12\x63\x1A\x5C\xF5\xD3\xED'
        G = b'\x04\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xd9\xd3\xce\x7e\xa2\xc5\xe9\x29\xb2\x61\x7c\x6d\x7e\x4d\x3d\x92\x4c\xd1\x48\x77\x2c\xdd\x1e\xe0\xb4\x86\xa0\xb8\xa1\x19\xae\x20'
        h = b'\x08'
    elif (args.command == 'x448'):
        P = b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        A = utils.int_to_bytes(0x98AA)
        N = b'\x3f\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x7c\xca\x23\xe9\xc4\x4e\xdb\x49\xae\xd6\x36\x90\x21\x6c\xc2\x72\x8d\xc5\x8f\x55\x23\x78\xc2\x92\xab\x58\x44\xf3'
        G = b'\x04\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x1a\x5b\x7b\x45\x3d\x22\xd7\x6f\xf7\x7a\x67\x50\xb1\xc4\x12\x13\x21\x0d\x43\x46\x23\x7e\x02\xb8\xed\xf6\xf3\x8d\xc2\x5d\xf7\x60\xd0\x45\x55\xf5\x34\x5d\xae\xcb\xce\x6f\x32\x58\x6e\xab\x98\x6c\xf6\xb1\xf5\x95\x12\x5d\x23\x7d'
        h = b'\x04'
    oid = b'\x06\x0A\x04\x00\x7F\x00\x07\x02\x02\x02\x02\x03'
    p_data = b'\x81' + bytes([len(P)]) + P
    a_data = b'\x82' + bytes([len(A)]) + A
    g_data = b'\x84' + bytes([len(G)]) + G
    n_data = b'\x85' + bytes([len(N)]) + N
    h_data = b'\x87' + bytes([len(h)]) + h

    cdata =  b'\x5F\x29\x01\x00'
    cdata += b'\x42\x0C\x55\x54\x44\x55\x4D\x4D\x59\x30\x30\x30\x30\x31'
    cdata += b'\x7f\x49\x81' + bytes([len(oid)+len(p_data)+len(a_data)+len(g_data)+len(n_data)+len(h_data)]) + oid + p_data + a_data + g_data + n_data + h_data
    cdata += b'\x5F\x20\x0C\x55\x54\x44\x55\x4D\x4D\x59\x30\x30\x30\x30\x31'
    ret = picohsm.send(command=0x46, p1=args.key, data=list(cdata))

def main(args):
    sys.stderr.buffer.write(b'Pico HSM Tool v1.10\n')
    sys.stderr.buffer.write(b'Author: Pol Henarejos\n')
    sys.stderr.buffer.write(b'Report bugs to https://github.com/polhenarejos/pico-hsm/issues\n')
    sys.stderr.buffer.write(b'\n\n')

    picohsm = PicoHSM(args.pin)

    # Following commands may raise APDU exception on error
    if (args.command == 'initialize'):
        initialize(picohsm, args)
    elif (args.command == 'attestate'):
        attestate(picohsm, args)
    elif (args.command == 'pki'):
        pki(picohsm, args)
    elif (args.command == 'datetime'):
        rtc(picohsm, args)
    elif (args.command == 'options'):
        opts(picohsm, args)
    elif (args.command == 'secure'):
        secure(picohsm, args)
    elif (args.command == 'cipher'):
        cipher(picohsm, args)
    elif (args.command == 'x25519' or args.command == 'x448'):
        x25519(picohsm, args)


def run():
    args = parse_args()
    main(args)

if __name__ == "__main__":
    run()
