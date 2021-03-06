#!/usr/bin/env python2.7

# Copyright 2015, Google Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following disclaimer
# in the documentation and/or other materials provided with the
# distribution.
#     * Neither the name of Google Inc. nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Read from stdin a set of colon separated http headers:
   :path: /foo/bar
   content-type: application/grpc
   Write a set of strings containing a hpack encoded http2 frame that
   represents said headers."""

import json
import sys
import argparse

def append_never_indexed(payload_line, n, count, key, value):
  payload_line.append(0x10)
  assert(len(key) <= 126)
  payload_line.append(len(key))
  payload_line.extend(ord(c) for c in key)
  assert(len(value) <= 126)
  payload_line.append(len(value))
  payload_line.extend(ord(c) for c in value)

def append_inc_indexed(payload_line, n, count, key, value):
  payload_line.append(0x40)
  assert(len(key) <= 126)
  payload_line.append(len(key))
  payload_line.extend(ord(c) for c in key)
  assert(len(value) <= 126)
  payload_line.append(len(value))
  payload_line.extend(ord(c) for c in value)

def append_pre_indexed(payload_line, n, count, key, value):
  payload_line.append(0x80 + 61 + count - n)

_COMPRESSORS = {
  'never': append_never_indexed,
  'inc': append_inc_indexed,
  'pre': append_pre_indexed,
}

argp = argparse.ArgumentParser('Generate header frames')
argp.add_argument('--set_end_stream', default=False, action='store_const', const=True)
argp.add_argument('--no_framing', default=False, action='store_const', const=True)
argp.add_argument('--compression', choices=sorted(_COMPRESSORS.keys()), default='never')
argp.add_argument('--hex', default=False, action='store_const', const=True)
args = argp.parse_args()

# parse input, fill in vals
vals = []
for line in sys.stdin:
  line = line.strip()
  if line == '': continue
  if line[0] == '#': continue
  key_tail, value = line[1:].split(':')
  key = (line[0] + key_tail).strip()
  value = value.strip()
  vals.append((key, value))

# generate frame payload binary data
payload_bytes = []
if not args.no_framing:
  payload_bytes.append([]) # reserve space for header
payload_len = 0
n = 0
for key, value in vals:
  payload_line = []
  _COMPRESSORS[args.compression](payload_line, n, len(vals), key, value)
  n += 1
  payload_len += len(payload_line)
  payload_bytes.append(payload_line)

# fill in header
if not args.no_framing:
  flags = 0x04  # END_HEADERS
  if args.set_end_stream:
    flags |= 0x01  # END_STREAM
  payload_bytes[0].extend([
      (payload_len >> 16) & 0xff,
      (payload_len >> 8) & 0xff,
      (payload_len) & 0xff,
      # header frame
      0x01,
      # flags
      flags,
      # stream id
      0x00,
      0x00,
      0x00,
      0x01
  ])

hex_bytes = [ord(c) for c in "abcdefABCDEF0123456789"]

def esc_c(line):
  out = "\""
  last_was_hex = False
  for c in line:
    if 32 <= c < 127:
      if c in hex_bytes and last_was_hex:
        out += "\"\""
      if c != ord('"'):
        out += chr(c)
      else:
        out += "\\\""
      last_was_hex = False
    else:
      out += "\\x%02x" % c
      last_was_hex = True
  return out + "\""

# dump bytes
if args.hex:
  all_bytes = []
  for line in payload_bytes:
    all_bytes.extend(line)
  print '{%s}' % ', '.join('0x%02x' % c for c in all_bytes)
else:
  for line in payload_bytes:
    print esc_c(line)
