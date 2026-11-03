"""Dumps the file descriptors and the deterministic encoding of a filled sample of every ABCI
Request/Response type, as JSON, for comparing two builds of bigchaindb-abci's _pb2 modules.

Usage: python -I dump_abci_pb2.py <dir containing abci_pb> > dump.json
"""
import json
import sys

sys.path.insert(0, sys.argv[1])

from google.protobuf.descriptor import FieldDescriptor  # noqa: E402
from google.protobuf.internal import api_implementation  # noqa: E402

import abci_pb.v0_22_8.types_pb2 as types_v0_22_8  # noqa: E402
import abci_pb.v0_31_5.github.com.tendermint.tendermint.abci.types.types_pb2 as types_v0_31_5  # noqa: E402

INTEGER_SAMPLES = {
    FieldDescriptor.TYPE_INT32: -2 ** 31, FieldDescriptor.TYPE_SINT32: -12345,
    FieldDescriptor.TYPE_SFIXED32: -7, FieldDescriptor.TYPE_UINT32: 2 ** 32 - 1,
    FieldDescriptor.TYPE_FIXED32: 2 ** 31, FieldDescriptor.TYPE_INT64: -2 ** 63,
    FieldDescriptor.TYPE_SINT64: -2 ** 40, FieldDescriptor.TYPE_SFIXED64: -9,
    FieldDescriptor.TYPE_UINT64: 2 ** 64 - 1, FieldDescriptor.TYPE_FIXED64: 2 ** 63,
}


def get_scalar_sample(field, index):
    if field.type == FieldDescriptor.TYPE_STRING:
        return '{}-{}-ü'.format(field.name, index)
    if field.type == FieldDescriptor.TYPE_BYTES:
        return '{}-{}'.format(field.name, index).encode() + bytes([0, 255])
    if field.type == FieldDescriptor.TYPE_BOOL:
        return True
    if field.type == FieldDescriptor.TYPE_ENUM:
        return field.enum_type.values[-1].number
    if field.type in (FieldDescriptor.TYPE_DOUBLE, FieldDescriptor.TYPE_FLOAT):
        return 1.5
    return INTEGER_SAMPLES[field.type] + index


def fill_message(message, depth=0):
    for field in message.DESCRIPTOR.fields:
        if field.containing_oneof is not None and field.containing_oneof.fields[0] is not field:
            continue
        repeated = field.is_repeated
        if field.type == FieldDescriptor.TYPE_MESSAGE:
            if depth >= 4:
                continue
            if field.message_type.GetOptions().map_entry:
                raise NotImplementedError('map field ' + field.full_name)
            if repeated:
                for _ in range(2):
                    fill_message(getattr(message, field.name).add(), depth + 1)
            else:
                fill_message(getattr(message, field.name), depth + 1)
                getattr(message, field.name).SetInParent()
        elif repeated:
            getattr(message, field.name).extend(get_scalar_sample(field, index) for index in range(2))
        else:
            setattr(message, field.name, get_scalar_sample(field, 0))


def dump_module(module):
    samples = {}
    for wrapper_name in ('Request', 'Response'):
        wrapper_type = getattr(module, wrapper_name)
        for field in wrapper_type.DESCRIPTOR.oneofs_by_name['value'].fields:
            wrapper = wrapper_type()
            fill_message(getattr(wrapper, field.name))
            getattr(wrapper, field.name).SetInParent()
            encoded = wrapper.SerializeToString(deterministic=True)
            assert wrapper_type.FromString(encoded) == wrapper
            samples['{}.{}'.format(wrapper_name, field.name)] = encoded.hex()
    return samples


def collect_files(file_descriptor, files):
    for dependency in file_descriptor.dependencies:
        collect_files(dependency, files)
    if not file_descriptor.name.startswith('google/protobuf/'):
        files[file_descriptor.name] = file_descriptor.serialized_pb.hex()
    return files


files = {}
collect_files(types_v0_22_8.DESCRIPTOR, files)
collect_files(types_v0_31_5.DESCRIPTOR, files)
json.dump({
    'implementation': api_implementation.Type(),
    'files': files,
    'samples': {'v0_22_8': dump_module(types_v0_22_8), 'v0_31_5': dump_module(types_v0_31_5)},
}, sys.stdout, indent=1, sort_keys=True)
