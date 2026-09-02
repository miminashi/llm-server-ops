#!/usr/bin/env python3
"""Shard_Rewrite の shard 1 から glm5-next.attention.head_count_kv を 45 要素に詰める。

PR #27773 の conversion/glm.py は head_count_kv を num_hidden_layers (=45) 個で書くが、
unsloth の GGUF は NextN ブロックを含む block_count (=46) 個で書いている。このため
#27773 は 'key glm5-next.attention.head_count_kv has wrong array length; expected 45, got 46'
で読み込みに失敗する。ここでは末尾 1 要素 (NextN ブロックぶん) を落とすだけの
バイト単位パッチを当てる。他の per-layer 配列 (swiglu_clamp_exp / _shexp) は
#27773 側も block_count=46 で書くのでそのまま。

usage: patch_shard1.py <in.gguf> <out.gguf>
"""
import struct, sys
sys.path.insert(0, '/home/ubuntu/projects/llm-server-ops/src/llama.cpp/gguf-py')
from gguf import GGUFReader
from gguf.constants import GGUFValueType

KEY = 'glm5-next.attention.head_count_kv'
src, dst = sys.argv[1], sys.argv[2]

r = GGUFReader(src)
f = r.fields[KEY]
start = f.offset
length = sum(int(p.nbytes) for p in f.parts)
raw = open(src, 'rb').read()
field = raw[start:start + length]

# 構造検証: key_len(u64) | key | value_type(u32=ARRAY) | elem_type(u32=INT32) | count(u64) | int32 * count
klen = struct.unpack_from('<Q', field, 0)[0]
assert field[8:8 + klen].decode() == KEY, 'key mismatch'
p = 8 + klen
vtype, etype = struct.unpack_from('<II', field, p); p += 8
assert vtype == GGUFValueType.ARRAY and etype == GGUFValueType.INT32, (vtype, etype)
cnt_off = p
count = struct.unpack_from('<Q', field, p)[0]; p += 8
assert count == 46 and p + 4 * count == length, (count, p, length)
vals = list(struct.unpack_from('<46i', field, p))
print('before:', count, vals)

new_field = bytearray(field[:length - 4])
struct.pack_into('<Q', new_field, cnt_off, count - 1)
open(dst, 'wb').write(raw[:start] + bytes(new_field) + raw[start + length:])
print('after :', count - 1, vals[:-1], '(dropped', vals[-1], ')')
print(f'{src} {len(raw)} B -> {dst} {len(raw) - 4} B')

chk = GGUFReader(dst)
print('verify:', len(chk.fields[KEY].contents()), 'entries, arch =',
      chk.fields['general.architecture'].contents())
