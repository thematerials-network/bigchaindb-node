"""Writes the FileDescriptorProtos embedded in bigchaindb-abci 1.0.5's generated _pb2 modules to a
FileDescriptorSet, so protoc can regenerate them without the (modified, unpublished) .proto sources.

Usage: python -I extract_abci_descriptors.py <dir containing the original abci_pb> <output .pb>
"""
import os
import sys

# The 2018 modules only load with the pure-Python protobuf implementation.
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
sys.path.insert(0, sys.argv[1])

from google.protobuf import descriptor_pb2  # noqa: E402

import abci_pb.v0_22_8.types_pb2 as types_v0_22_8  # noqa: E402
import abci_pb.v0_31_5.github.com.tendermint.tendermint.abci.types.types_pb2 as types_v0_31_5  # noqa: E402

descriptor_set = descriptor_pb2.FileDescriptorSet()
added = set()


def add_file(file_descriptor):
    for dependency in file_descriptor.dependencies:
        add_file(dependency)
    if file_descriptor.name in added:
        return
    added.add(file_descriptor.name)
    # Well-known types come from the current runtime, not from the 2018 copies.
    if file_descriptor.name.startswith('google/protobuf/'):
        return
    descriptor_set.file.append(descriptor_pb2.FileDescriptorProto.FromString(file_descriptor.serialized_pb))


add_file(types_v0_22_8.DESCRIPTOR)
add_file(types_v0_31_5.DESCRIPTOR)

with open(sys.argv[2], 'wb') as output:
    output.write(descriptor_set.SerializeToString())
for file in descriptor_set.file:
    print(file.name)
