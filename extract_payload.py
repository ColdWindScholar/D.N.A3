import hashlib
import os
import os.path
import struct
import subprocess
import sys
import threading
import time
import zipfile
from rich.console import Console

if os.name == 'nt':
    import bz2

    try:
        import lzma
    except ImportError:
        from backports import lzma
import update_metadata_pb2

PROGRAMS = ['bzcat', 'xzcat']
BRILLO_MAJOR_PAYLOAD_VERSION = 2


class PayloadError(Exception):
    ...


class Payload(object):
    class _PayloadHeader(object):
        _MAGIC = b'CrAU'

        def __init__(self):
            self.version = None
            self.manifest_len = None
            self.metadata_signature_len = None
            self.size = None

        def ReadFromPayload(self, payload_file):
            magic = payload_file.read(4)
            if magic != self._MAGIC:
                raise PayloadError('Invalid payload magic: %s' % magic)
            self.version = struct.unpack('>Q', payload_file.read(8))[0]
            self.manifest_len = struct.unpack('>Q', payload_file.read(8))[0]
            self.size = 20
            self.metadata_signature_len = 0
            if self.version != BRILLO_MAJOR_PAYLOAD_VERSION:
                raise PayloadError('Unsupported payload version (%d)' % self.version)
            self.size += 4
            self.metadata_signature_len = struct.unpack('>I', payload_file.read(4))[0]

    def __init__(self, payload_file):
        self.payload_file = payload_file
        self.header = None
        self.manifest = None
        self.data_offset = None
        self.metadata_signature = None
        self.metadata_size = None

    def _ReadManifest(self):
        return self.payload_file.read(self.header.manifest_len)

    def _ReadMetadataSignature(self):
        self.payload_file.seek(self.header.size + self.header.manifest_len)
        return self.payload_file.read(self.header.metadata_signature_len)

    def ReadDataBlob(self, offset, length):
        self.payload_file.seek(self.data_offset + offset)
        return self.payload_file.read(length)

    def Init(self):
        self.header = self._PayloadHeader()
        self.header.ReadFromPayload(self.payload_file)
        manifest_raw = self._ReadManifest()
        self.manifest = update_metadata_pb2.DeltaArchiveManifest()
        self.manifest.ParseFromString(manifest_raw)
        metadata_signature_raw = self._ReadMetadataSignature()
        if metadata_signature_raw:
            self.metadata_signature = update_metadata_pb2.Signatures()
            self.metadata_signature.ParseFromString(metadata_signature_raw)
        self.metadata_size = self.header.size + self.header.manifest_len
        self.data_offset = self.metadata_size + self.header.metadata_signature_len


def decompress_payload(command, data, size, hash):
    p = subprocess.Popen([command, '-'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    r = p.communicate(data)[0]
    if len(r) != size:
        print('Unexpected size %d %d' % (len(r), size))
    elif hashlib.sha256(data).digest() != hash:
        print('Hash mismatch')
    return r


def parse_payload(payload_f, partition, out_f):
    BLOCK_SIZE = 4096
    for operation in partition.operations:
        e = operation.dst_extents[0]
        data = payload_f.ReadDataBlob(operation.data_offset, operation.data_length)
        out_f.seek(e.start_block * BLOCK_SIZE)
        if operation.type == update_metadata_pb2.InstallOperation.REPLACE:
            out_f.write(data)
        elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_XZ:
            if os.name == 'posix':
                r = decompress_payload('xzcat', data, e.num_blocks * BLOCK_SIZE, operation.data_sha256_hash)
            if os.name == 'nt':
                dec = lzma.LZMADecompressor()
                r = dec.decompress(data)
            out_f.write(r)
        elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_BZ:
            if os.name == 'posix':
                r = decompress_payload('bzcat', data, e.num_blocks * BLOCK_SIZE, operation.data_sha256_hash)
            if os.name == 'nt':
                dec = bz2.BZ2Decompressor()
                r = dec.decompress(data)
            out_f.write(r)
        elif operation.type == update_metadata_pb2.InstallOperation.ZERO:
            out_f.write(b'\x00' * (e.num_blocks * BLOCK_SIZE))
        else:
            raise PayloadError('Unhandled operation type ({} - {})'.format(operation.type,
                                                                           update_metadata_pb2.InstallOperation.Type.Name(
                                                                               operation.type)))


def run(fname, payload, p):
    out_f = open(fname, 'wb')
    try:
        parse_payload(payload, p, out_f)
        print(' [Success]')
    except PayloadError as e:
        print(' [Failed: %s]' % e)
        out_f.close()
        os.unlink(fname)


def main(filename, output_dir, partition=None):
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    if filename.endswith('.zip'):
        print("Extracting 'payload.bin' from OTA file ...")
        ota_zf = zipfile.ZipFile(filename)
        payload_file = open(ota_zf.extract('payload.bin', output_dir), 'rb')
    else:
        payload_file = open(filename, 'rb')
    payload = Payload(payload_file)
    payload.Init()
    for p in payload.manifest.partitions:
        name = p.partition_name + '.img'
        if partition is not None and name != partition:
            continue
        fname = os.path.join(output_dir, name)
        with Console().status(f"[yellow]正在提取{name}[/]"):
            run(fname, payload, p)


def info(filename):
    if os.path.basename(filename) == 'payload.bin':
        payload_file = open(filename, 'rb')
    else:
        sys.exit()
    if payload_file:
        name = []
        payload = Payload(payload_file)
        payload.Init()
        for p in payload.manifest.partitions:
            name.append(p.partition_name + '.img')
        return name
