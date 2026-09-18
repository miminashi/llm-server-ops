import struct, sys
f = open(sys.argv[1], 'rb')
magic = f.read(4); ver = struct.unpack('<I', f.read(4))[0]
nt = struct.unpack('<Q', f.read(8))[0]; nkv = struct.unpack('<Q', f.read(8))[0]
print(f"magic={magic} version={ver} tensors={nt} kv={nkv}")
def rs():
    n = struct.unpack('<Q', f.read(8))[0]
    return f.read(n).decode('utf-8', 'replace')
T = {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
S = {0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
want = ('general.architecture','general.name','general.size_label','block_count','expert_count',
        'expert_used_count','embedding_length','head_count','context_length','feed_forward',
        'general.file_type','rope','nextn','quantization')
for _ in range(nkv):
    k = rs(); t = struct.unpack('<I', f.read(4))[0]
    if t == 8:
        v = rs()
    elif t == 9:
        et = struct.unpack('<I', f.read(4))[0]; n = struct.unpack('<Q', f.read(8))[0]
        if et == 8:
            for _ in range(n): rs()
        else:
            f.read(S.get(et, 4) * n)
        v = f"[{T.get(et, et)} x{n}]"
    else:
        v = struct.unpack('<' + T.get(t, 'I'), f.read(S.get(t, 4)))[0]
    if any(w in k for w in want):
        print(f"  {k} = {v}")
