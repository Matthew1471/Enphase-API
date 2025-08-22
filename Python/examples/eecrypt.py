#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This file is part of Enphase-API <https://github.com/Matthew1471/Enphase-API>
# Copyright (C) 2023-2025 Matthew1471!
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This example provides functionality to encrypt or decrypt Enphase® files.
"""

# We support command line arguments.
import argparse

# We use SHA-256 hashing to derive some keys.
import hashlib

# We use Enum decorators.
from enum import Enum

# We use the dataclass dunder.
from dataclasses import dataclass

# We generate secure random bytes.
import secrets

# We exit the program if help is chosen.
import sys

# We perform cryptographic functions.
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


KEYS = {
    'EEMasterKey' : {
        0: [
            bytes((0x25, 0xc8, 0xcc, 0xc2, 0x4b, 0x22, 0x21, 0xa8)),
            bytes((0xe6, 0x84, 0x74, 0x4a, 0x1d, 0x84, 0xea, 0x4c)),
            bytes((0x93, 0x6f, 0x45, 0xd3, 0xfc, 0xd0, 0x3a, 0x90)),
            bytes((0x8f, 0x28, 0x66, 0x19, 0x60, 0xc7, 0x7f, 0x8f))
        ],
        1: [
            bytes((0x43, 0x70, 0xdd, 0x79, 0xa3, 0xd1, 0x0f, 0xef)),
            bytes((0xc4, 0x07, 0xc2, 0xc6, 0xeb, 0x95, 0xaf, 0xc4)),
            bytes((0xb5, 0x7f, 0x6a, 0x91, 0x8e, 0x76, 0x2c, 0x0e)),
            bytes((0x67, 0xee, 0x08, 0x4b, 0x52, 0x39, 0xed, 0x6c))
        ]
    },
    'EEBootKey' : {
        0: [
            bytes((0xa2, 0xde, 0xca, 0x5c, 0x59, 0xe4, 0x78, 0xf3)),
            bytes((0x99, 0x1a, 0x40, 0xf1, 0x8f, 0x5f, 0x3b, 0x12)),
            bytes((0x7f, 0xf1, 0x37, 0x19, 0x67, 0x90, 0xf8, 0x1a)),
            bytes((0xfc, 0x4e, 0x39, 0x87, 0xf2, 0x64, 0x5b, 0x39))
        ],
        1: [
            bytes((0x3d, 0xf5, 0x12, 0x8e, 0x4a, 0x33, 0x99, 0xd6)),
            bytes((0x4f, 0x10, 0xab, 0xaa, 0x1d, 0x4c, 0x8a, 0x4a)),
            bytes((0xac, 0x6c, 0xcd, 0x45, 0xfb, 0x98, 0x33, 0x8a)),
            bytes((0xf1, 0x39, 0x61, 0xf4, 0xa4, 0xe7, 0x2d, 0x09))
        ]
    },
    'EEPackageKey': {
        0: [
            bytes((0x69, 0x11, 0x52, 0xa5, 0xaf, 0x51, 0x1c, 0x62)),
            bytes((0x5d, 0x24, 0xbe, 0xb9, 0xc7, 0x3b, 0xc9, 0x6e)),
            bytes((0x23, 0x68, 0xb8, 0xc4, 0xcf, 0x1c, 0x2b, 0x8e)),
            bytes((0x56, 0x0c, 0xc5, 0xef, 0x40, 0x85, 0xb0, 0xb5))
        ],
        1: [
            bytes((0xe3, 0xb9, 0x00, 0x9c, 0x24, 0xf8, 0x7c, 0x47)),
            bytes((0x39, 0xa5, 0xaa, 0x44, 0x37, 0x3c, 0x4d, 0x96)),
            bytes((0x75, 0xf3, 0x73, 0xd0, 0x53, 0x97, 0x6b, 0xd2)),
            bytes((0x41, 0xf8, 0x7c, 0x50, 0xac, 0x20, 0xa9, 0xbb))
        ]
    },
    'EEEnlightenKey': {
        0: [
            bytes((0x63, 0x34, 0x7d, 0xff, 0x44, 0x45, 0xd9, 0x8d)),
            bytes((0x93, 0x6d, 0x8f, 0x0f, 0x9c, 0x46, 0x5d, 0x4a)),
            bytes((0x1c, 0x13, 0xb1, 0x75, 0x54, 0xca, 0xae, 0x97)),
            bytes((0x18, 0x9e, 0xa2, 0x68, 0x33, 0x90, 0x6d, 0x4a))
        ],
        1: [
            bytes((0x2f, 0x36, 0x2c, 0x41, 0x30, 0x31, 0xa3, 0x3a)),
            bytes((0xca, 0x4b, 0xae, 0x67, 0x30, 0x5c, 0x03, 0xe8)),
            bytes((0x68, 0x38, 0xef, 0x82, 0x38, 0x9b, 0xd5, 0xa7)),
            bytes((0x01, 0x70, 0x53, 0x80, 0x46, 0x88, 0x86, 0x4a))
        ]
    }
}

# Faithful reproduction of the Enphase Crypto Tool help.
HELP_TEXT = """Enphase Crypto Tool v1.0.0

# USAGE
____

eecrypt [--action <encrypt | decrypt | gen_sig | chk_sig | random> --key_type <pack | enln | mstr | boot | cust> --key_index <0 | 1> --input <file_path> --output <file_path> --signature <file_path>] [--key_size <128|256>] [--crypt_mode <cbc|ecb>] [--random_bytes <number_of_bytes>] [--key <file_path>] [--help]

The --action flag should have one of the following arguments:

        encrypt encrypt a file
        decrypt decrypt a file
        gen_sig generate a signature from a file
        chk_sig check a file signature
        random  output random bytes

The --key_type flag should have one of the following arguments:

        pack    Use the envoy upgrade package key
        enln    Use the envoy to enlighten comm key
        mstr    Use the Enphase master key
        boot    Use the Enphase pcu boot key
        none    Use no key (only used for signatures)
        cust    Use a custom key (passed in via --key param)

The --key_index flag should have one of the following arguments:

        0       key index 0
        1       key index 1

The --input flag should have the following argument:

        The file name

The --output flag should have the following argument:

        The file name

The --signature flag should have the following argument:

        The file name

The --key_size flag is optional, but if set, should have one of the following arguments:

        128     key size 128 bits (defaults to this if the flag is not set)
        256     key size 256 bits

The --crypt_mode flag is optional, but if set, should have one of the following arguments:

        cbc     Cypher Block Chaining (defaults to this if the flag is not set)
        ecb     Electronic Code Book

The --random_bytes flag is optional, but if set, should have the following argument:

        The number of bytes to output (if not set, 32 bytes will be output)

The --key flag is only required if --key_type is set to cust, then it should be:

        The file name containing the key
"""

@dataclass
class FileHeader:
    type_id: int
    key_index: int
    key_size: int
    crypt_mode: int
    iv: bytes
    file_size: int

    FILE_MAGIC = bytes([
        0xEE, 0xEF,
        ord('-'), 0x20, 0x14, # Year 2014
        ord('-'), 0x06,       # Month June
        ord('-'), 0x05,       # Day 5th
        ord('-'), 0x00, 0x00  # Time 00:00
    ])

    class CryptMode(Enum):
        CBC = 0
        ECB = 1

    CRYPT_MODE_NAMES = {
        0: 'CBC',
        1: 'ECB'
    }

    def to_bytes(self) -> bytes:
        return bytes().join([
            self.FILE_MAGIC,                          # Magic header
            b't', bytes([self.type_id]),              # Key Type
            b'i', self.key_index.to_bytes(2, 'big'),  # Key Index
            b'k', bytes([self.key_size]),             # Key Size
            b'm', bytes([self.crypt_mode]),           # Encryption Mode
            b'v', self.iv,                            # Initialization Vector
            b's', self.file_size.to_bytes(8, 'big'),  # File Size
            b'b'                                      # Payload Marker
        ])

    @staticmethod
    def expect_tag(actual: int, expected: str):
        if actual != ord(expected):
            raise ValueError(f'"{expected}" tag expected but "{chr(actual)}" found.')

    @staticmethod
    def from_bytes(data: bytes) -> 'FileHeader':
        if len(data) != 48:
            raise ValueError('Header must be exactly 48 bytes.')

        # Magic/Signature bytes.
        magic_bytes = data[0:12]
        if magic_bytes != FileHeader.FILE_MAGIC:
            raise ValueError('File header magic bytes do not match expected format.')

        # Metadata used during decryption.
        type_id_tag = data[12]
        FileHeader.expect_tag(type_id_tag, 't')
        type_id = data[13]

        key_index_tag = data[14]
        FileHeader.expect_tag(key_index_tag, 'i')
        key_index = int.from_bytes(data[15:17], 'big')

        key_size_tag = data[17]
        FileHeader.expect_tag(key_size_tag, 'k')
        key_size = data[18]

        crypt_mode_tag = data[19]
        FileHeader.expect_tag(crypt_mode_tag, 'm')
        crypt_mode = data[20]

        iv_tag = data[21]
        FileHeader.expect_tag(iv_tag, 'v')
        iv = data[22:38]

        file_size_tag = data[38]
        FileHeader.expect_tag(file_size_tag, 's')
        file_size = int.from_bytes(data[39:47], 'big')

        byte_tag = data[47]
        FileHeader.expect_tag(byte_tag, 'b')

        # Return an initialised FileHeader object.
        return FileHeader(
            type_id=type_id,
            key_index=key_index,
            key_size=key_size,
            crypt_mode=crypt_mode,
            iv=iv,
            file_size=file_size
        )

    def __str__(self):
        result = []

        result.append('📦 Enphase Encrypted File Header')
        result.append('-' * 32)

        result.append('🧙 Magic Bytes:')

        # Print first two bytes.
        result.append(f'  Bytes 01-02: 0x{FileHeader.FILE_MAGIC[0]:02X}, 0x{FileHeader.FILE_MAGIC[1]:02X}')

        # Extract date and time components.
        # Interpret year as two separate bytes: 0x20 and 0x14 → 2014.
        year = f'{FileHeader.FILE_MAGIC[3]:02X}{FileHeader.FILE_MAGIC[4]:02X}'
        month = FileHeader.FILE_MAGIC[6]
        day = FileHeader.FILE_MAGIC[8]
        hour = FileHeader.FILE_MAGIC[10]
        minute = FileHeader.FILE_MAGIC[11]

        # Format date string.
        date_str = f'{year}-{month:02}-{day:02} {hour:02}:{minute:02}'
        hex_repr = ', '.join(f'0x{b:02X}' for b in FileHeader.FILE_MAGIC[2:12])
        result.append(f'  Bytes 03–11: {date_str} ({hex_repr})')

        # Print remaining header fields.
        key_type_names = {
            0: 'None',
            1: 'Custom Key',
            2: 'Package Key',
            3: 'Enlighten Key',
            4: 'Master Key',
            5: 'Boot Key'
        }
        result.append(f'\n🆔 Bytes 12-13: Key Type (t) = {key_type_names.get(self.type_id, "Unknown")} ({self.type_id})')

        result.append(f'🔢 Bytes 14-16: Key Index (i) = {self.key_index}')
        result.append(f'🔑 Bytes 17-18: Key Size (k) = {self.key_size * 8} bits ({self.key_size})')
        result.append(f'🔐 Bytes 19-20: Crypt Mode (m) = {FileHeader.CRYPT_MODE_NAMES.get(self.crypt_mode, "Unknown")} ({self.crypt_mode})')
        result.append(f'🧊 Bytes 21-37: IV (v) = 0x{self.iv.hex()}')

        file_size_string = f'{self.file_size:,} bytes' if self.file_size != 0xFFFFFFFFFFFFFFFF else 'Unknown'
        result.append(f'📏 Bytes 38-46: File Size (s) = {file_size_string}')

        result.append('\n🧱 Byte 47: Binary Start (b)')

        return '\n'.join(result)

def _get_cipher(key: bytes, iv: bytes, crypt_mode: FileHeader.CryptMode) -> Cipher:
    if crypt_mode == FileHeader.CryptMode.CBC:
        return Cipher(algorithms.AES(key), modes.CBC(iv))
    elif crypt_mode == FileHeader.CryptMode.ECB:
        return Cipher(algorithms.AES(key), modes.ECB())
    else:
        raise ValueError('crypt mode unsupported!')

def encrypt(key: bytes, iv: bytes, crypt_mode: FileHeader.CryptMode, data: bytes) -> bytes:
    cipher = _get_cipher(key, iv, crypt_mode)
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()

def decrypt(key: bytes, iv: bytes, crypt_mode: FileHeader.CryptMode, data: bytes) -> bytes:
    cipher = _get_cipher(key, iv, crypt_mode)
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()

def generate_key(type_id : int, key_index : int) -> bytes:
    # Lookup the relevant key.
    key_map = {
        2: 'EEPackageKey',
        3: 'EEEnlightenKey',
        4: 'EEMasterKey',
        5: 'EEBootKey',
    }

    # Get the 4 blocks.
    blocks = KEYS[key_map.get(type_id)][key_index]

    # Generate sequences: mirrored + 3 rotations.
    sequences = [blocks + blocks[::-1]]
    sequences += [blocks[i:] + blocks[:i] for i in range(1, 4)]

    # Perform key derivation routine.
    output = b''
    for sequence in sequences:
        sha = hashlib.sha256()
        for part in sequence:
            sha.update(part)
        if output:
            sha.update(output)
        output = sha.digest()

    return output

def main():
    # Create an instance of argparse to parse any command line arguments.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--help', '--h', '-h', action='store_true')
    parser.add_argument('--action', '--a', '-a')
    parser.add_argument('--key_type', '-t')
    parser.add_argument('--key_index')
    parser.add_argument('--key_size', '-l', default='128')
    parser.add_argument('--input', '--i', '-f')
    parser.add_argument('--output', '--o', '-o')
    parser.add_argument('--signature', '--s')
    parser.add_argument('--crypt_mode', '-m', default='cbc')
    parser.add_argument('--random_bytes', '--r', '-r', default='32')
    parser.add_argument('--key', '-k')
    parser.add_argument('--bare', '-bare', '--b', action='store_true')

    # Handle any known command line arguments.
    args, unrecognised_options = parser.parse_known_args()

    # We faithfully reproduce the original eecrypt quirky logic and bugs.
    if len(unrecognised_options) > 0:
        for unrecognised_option in unrecognised_options:
            print('./eecrypt: unrecognized option \'' + str(unrecognised_option) + '\'')
        print(HELP_TEXT)
        sys.exit(1)

    if (
        len(sys.argv) == 1 or
        args.help or
        args.action not in [None, 'help', 'encrypt', 'decrypt', 'gen_sig', 'chk_sig', 'random'] or
        args.key_type not in [None, 'pack', 'enln', 'mstr', 'boot', 'none', 'cust'] or
        args.key_index not in [None, '0', '1'] or
        args.key_size not in ['128', '256'] or
        args.crypt_mode not in ['cbc','ecb']
    ):
        print(HELP_TEXT)
        sys.exit(1)

    key_type_map = {
        'cust': 1,
        'pack': 2,
        'enln': 3,
        'mstr': 4,
        'boot': 5,
    }

    if args.action == 'help':
        print(HELP_TEXT)
        sys.exit(1)
    elif args.action == 'encrypt':
        if args.key_type is None:
            print('key type unknown!')
            print(HELP_TEXT)
            sys.exit(1)

        if args.key_index is None:
            print('key index: 2 is not supported!')
            print(HELP_TEXT)
            sys.exit(1)

        if args.key_type == 'none':
            print('Segmentation fault')
            sys.exit(1)

        # Did the user specify an input filename?
        if args.input:
            input_stream = open(args.input, 'rb')
        else:
            # Read from stdin instead.
            input_stream = sys.stdin.buffer

        with input_stream:
            # Read payload bytes from stream.
            plaintext = input_stream.read()

        if args.crypt_mode == 'cbc':
            iv = secrets.token_bytes(16)
        else:
            # 16 null bytes.
            iv = bytes(16)

        header = FileHeader(
            type_id=key_type_map.get(args.key_type),
            key_index=int(args.key_index),
            key_size=int(args.key_size) // 8,
            crypt_mode=FileHeader.CryptMode[args.crypt_mode.upper()].value,
            iv=iv,
            file_size=len(plaintext)
        )

        # Generate Encryption/Decryption key (truncate the key to the required key size).
        if args.key_type != 'cust':
            key = generate_key(header.type_id, header.key_index)[:header.key_size]
        else:
            # Load a custom key.
            with open(args.key_file, 'rb') as f:
                key = f.read()[:header.key_size]

        # The data must be padded (original pads with nulls).
        block_size = 16
        padding_length = (block_size - len(plaintext) % block_size) % block_size
        padded_plaintext = plaintext + bytes(padding_length)

        try:
            ciphertext = encrypt(key, header.iv, FileHeader.CryptMode(header.crypt_mode), padded_plaintext)
        except Exception as e:
            print(e)
            print('cannot get crypt engine')
            print(HELP_TEXT)
            sys.exit(1)

        # Write to the output.
        if args.output:
            with open(args.output, 'wb') as output_file:
                output_file.write(header.to_bytes())
                output_file.write(ciphertext)
        else:
            sys.stdout.buffer.write(header.to_bytes())
            sys.stdout.buffer.write(ciphertext)
    elif args.action == 'decrypt':
        # Did the user specify an input filename?
        if args.input:
            input_stream = open(args.input, 'rb')
        else:
            # Read from stdin instead.
            input_stream = sys.stdin.buffer

        with input_stream:
            # Read the header.
            header_bytes = input_stream.read(48)

            try:
                header = FileHeader.from_bytes(header_bytes)
            except Exception as _:
                print('input crypt signature isn\'t valid.')
                print(HELP_TEXT)
                sys.exit(1)

            # Read remaining payload bytes from stream.
            ciphertext = input_stream.read()

        # Generate Encryption/Decryption key (truncate the key to the required key size).
        key = generate_key(header.type_id, header.key_index)[:header.key_size]

        try:
            plaintext = decrypt(key, header.iv, FileHeader.CryptMode(header.crypt_mode), ciphertext)
        except Exception as e:
            print(e)
            print('cannot get crypt engine')
            print(HELP_TEXT)
            sys.exit(1)

        if args.output:
            with open(args.output, 'wb') as output_file:
                output_file.write(plaintext[:header.file_size])
        else:
            # Debug the header.
            #print(str(header) + ':')

            sys.stdout.buffer.write(plaintext[:header.file_size])
    elif args.action == 'gen_sig':
        # We do not yet support key based signatures.
        sha256 = hashlib.sha256()
        
        # Did the user specify an input filename?
        if args.input:
            input_stream = open(args.input, 'rb')
        else:
            # Read from stdin instead.
            input_stream = sys.stdin.buffer

        with input_stream:
            while True:
                chunk = input_stream.read(4096)
                if not chunk:
                    break
                sha256.update(chunk)

        # Get raw digest bytes.
        digest_bytes = sha256.digest()

        if args.output:
            with open(args.output, 'wb') as output_file:
                output_file.write(digest_bytes)
        else:
            sys.stdout.buffer.write(digest_bytes)
    elif args.action == 'chk_sig':
        # We do not yet support key based signatures.
        sha256 = hashlib.sha256()

        # Read input data.
        if args.input:
            input_stream = open(args.input, 'rb')
        else:
            input_stream = sys.stdin.buffer

        with input_stream:
            while True:
                chunk = input_stream.read(4096)
                if not chunk:
                    break
                sha256.update(chunk)

        # Compute digest.
        computed_digest = sha256.digest()

        # Read expected signature.
        if args.signature:
            with open(args.signature, 'rb') as sig_file:
                expected_digest = sig_file.read()
        else:
            expected_digest = sys.stdin.buffer.read()

        # Compare digests.
        if computed_digest == expected_digest:
            sys.exit(0)
        else:
            print(HELP_TEXT)
            sys.exit(1)
    elif args.action == 'random':
        random_bytes = secrets.token_bytes(int(args.random_bytes))
        if args.output:
            with open(args.output, 'wb') as output_file:
                output_file.write(random_bytes)
        else:
            sys.stdout.buffer.write(random_bytes)
    else:
        print('ERR: eecrypt unknown program state!')
        print('ERR: please type eecrypt --help')
        # The help is not provided for this error.
        sys.exit(1)

# Launch the main function if invoked directly.
if __name__ == '__main__':
    main()
