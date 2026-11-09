"""Compile the real save decoders and exercise valid and hostile containers.

Set CC to a host C compiler; SANITIZE=1 enables ASan and UBSan.
Fixtures are generated here, with no game data or console dependencies.
"""
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zlib

root = Path(__file__).resolve().parents[1]


def u32(value):
    return struct.pack('<I', value)


def psu_entry(name, size, mode):
    data = bytearray(512)
    struct.pack_into('<HI', data, 0, mode, 0)  # size is at offset 4
    struct.pack_into('<I', data, 4, size)
    data[64:64 + len(name)] = name
    return data


def xps_entry(name, size, mode):
    data = bytearray(250)
    struct.pack_into('<H', data, 0, 250)
    data[2:2 + len(name)] = name
    struct.pack_into('<I', data, 66, size)
    struct.pack_into('>I', data, 78, mode << 16)
    return data


payload = b'SC' + bytes(8190)
fixtures = {}
fixtures['test.psu'] = (psu_entry(b'BASLUS-TEST', 3, 0x8427) +
                        psu_entry(b'.', 0, 0x8427) + psu_entry(b'..', 0, 0x8427) +
                        psu_entry(b'data.bin', len(payload), 0x8497) + payload)
mcs = bytearray(128)
mcs[0] = 0x51
struct.pack_into('<I', mcs, 4, len(payload))
mcs[8:10] = b'\xff\xff'
mcs[10:21] = b'BASLUS-TEST'
fixtures['test.mcs'] = mcs + payload
fixtures['test.psx'] = b'BASLUS-TEST' + bytes(54 - 11) + payload
fixtures['BASLUS-RAW'] = payload
psv1 = bytearray(132)
psv1[:4] = b'\0VSP'
struct.pack_into('<I', psv1, 60, 1)
psv1[100:111] = b'BASLUS-TEST'
fixtures['ps1.psv'] = psv1 + payload
psv2 = bytearray(236)
psv2[:4] = b'\0VSP'
struct.pack_into('<I', psv2, 60, 2)
struct.pack_into('<II', psv2, 120, 3, 0x8427)
psv2[128:139] = b'BASLUS-TEST'
struct.pack_into('<II', psv2, 184, len(payload), 0x8497)
psv2[192:200] = b'data.bin'
struct.pack_into('<I', psv2, 232, 236)
fixtures['ps2.psv'] = psv2 + payload
fixtures['test.xps'] = (u32(13) + b'SharkPortSave\0\0\0' + b'\0' + u32(0) + u32(0) + u32(0) + u32(0) +
                        xps_entry(b'BASLUS-TEST', 3, 0x8427) + xps_entry(b'data.bin', len(payload), 0x8497) + payload)

# This RC4 state is fixture data from mymc/Apollo, independent of the decoder.
state = bytearray.fromhex('''
5f1f856f31aa3b1821b9ce1c074c9cb4 81b8ef9859aef926e380a3292d735162
7c6446f4341af6e1ba3a0d82790a5c16 71498eac8c9f351945943f560c91000b
d7b0dd3966a176521357f3bb4ee5dcf0 6584b2d6df153c631d8914bdd236feb1
ca8ba4c69e674737426d6a039270057d 962f4090c4f13e3d01f7681ec3fc72b5
54cfe741e44d835512220978fadea706 0823bf0fccc19761c54ae6a011c2ea74
0287d5d19db77e386053958d2577105e 9b7fd86edaa22e204fcd8fcbb e5ae0ed
2c9ad4e2afd0a9e8ad7abca8f2eeebf5 a69928246c2b755df8d38617fbc07bb3
58dbc74bff0450e98869c92aabfd5b1b 8ad9ec27440e33c86b933248b63043a5
'''.replace(' ', '').replace('\n', ''))
assert len(state) == 256 and len(set(state)) == 256
cbs = bytearray(296)
cbs[:4] = b'CFU\0'
struct.pack_into('<I', cbs, 8, 296)
struct.pack_into('<I', cbs, 12, 64 + len(payload))
cbs[20:31] = b'BASLUS-TEST'
struct.pack_into('<I', cbs, 72, 0x8427)
centry = bytearray(64)
struct.pack_into('<II', centry, 16, len(payload), 0x8497)
centry[32:40] = b'data.bin'
encrypted = bytearray(zlib.compress(centry + payload))
a = b = 0
for index in range(len(encrypted)):
    a = (a + 1) & 255
    b = (b + state[a]) & 255
    state[a], state[b] = state[b], state[a]
    encrypted[index] ^= state[(state[a] + state[b]) & 255]
fixtures['test.cbs'] = cbs + encrypted

code = r'''
#include "save_archive.h"
#include "save_lzari.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void check(unsigned char *p, size_t n, const char *name, int valid) {
    SaveArchive save;
    unsigned char *copy=malloc(n?n:1); memcpy(copy,p,n);
    int result=saveArchiveParse(&save,copy,n,name);
    if(result != valid) { fprintf(stderr,"%s size %zu: got %d wanted %d\n",name,n,result,valid); abort(); }
    if(result) {
        assert(save.count==1 && save.files[0].size==8192);
        assert(!memcmp(save.files[0].data,"SC",2));
        assert(!strcmp(save.files[0].name,save.ps1?(!strcmp(name,"BASLUS-RAW")?"BASLUS-RAW":"BASLUS-TEST"):"data.bin"));
        if(!save.ps1) assert(!strcmp(save.folder.name,"BASLUS-TEST") && save.folder.mode==0x8427 && save.files[0].mode==0x8497);
    }
    saveArchiveFree(&save); free(copy);
}
int main(int argc,char **argv) {
    for(int a=1;a<argc;a++) {
        FILE *f=fopen(argv[a],"rb"); assert(f); fseek(f,0,SEEK_END);size_t n=ftell(f);rewind(f);
        unsigned char *p=malloc(n);assert(p&&fread(p,1,n,f)==n);fclose(f);
        const char *name=strrchr(argv[a],'/')+1;
        check(p,n,name,1);
        for(size_t cut=0;cut<300&&cut<n;cut++) check(p,cut,name,0);
        check(p,n-1,name,0);
        /* Mutate headers and filenames to exercise size arithmetic/path validation. */
        for(unsigned i=0;i<1024;i++) {
            unsigned char *copy=malloc(n);memcpy(copy,p,n);
            copy[(i*73)%(n<2000?n:2000)]^=(unsigned char)(i|1);
            SaveArchive save;saveArchiveParse(&save,copy,n,name);saveArchiveFree(&save);free(copy);
        }
        free(p);
    }
    unsigned char raw[8192]={ 'S','C' }, stream[16384], max[16480]={0};
    unsigned char unpacked[8232]={0};
    unpacked[0]=0;unpacked[1]=32;memcpy(unpacked+4,"data.bin",8);memcpy(unpacked+36,raw,sizeof(raw));
    int compressed=lzari(unpacked,sizeof(unpacked),stream,sizeof(stream));assert(compressed>4);
    memcpy(max,"Ps2PowerSave",12);memcpy(max+16,"BASLUS-TEST",11);
    max[84]=1;memcpy(max+88,stream,compressed);
    check(max,88+compressed,"test.max",1);
    check(max,90,"test.max",0);
    unsigned char tiny[4]={0xff,0xff,0xff,0x7f}, out[32];
    assert(unlzari(tiny,4,out,sizeof(out))<0);
    unsigned char *card=malloc(PS1_CARD_SIZE+3904);ps1CardFormat(card);
    assert(ps1CardOffset(card,PS1_CARD_SIZE)==0);
    assert(ps1CardAppend(card,"BASLUS-TEST",raw,sizeof(raw)));
    assert(!ps1CardAppend(card,"BASLUS-TEST",raw,sizeof(raw)));
    unsigned char multiblock[8192*3]={'S','C'};
    assert(ps1CardAppend(card,"BASLUS-THREE",multiblock,sizeof(multiblock)));
    assert(card[256]==0x51 && card[384]==0x52 && card[512]==0x53);
    assert(card[256+8]==2 && card[384+8]==3 && card[512+8]==0xff);
    for(unsigned i=0;i<36;i++){unsigned char sum=0;for(int j=0;j<128;j++)sum^=card[i*128+j];assert(!sum);}
    for(int i=0;i<11;i++){char name[21];snprintf(name,sizeof(name),"BASLUS-%d",i);assert(ps1CardAppend(card,name,raw,sizeof(raw)));}
    assert(!ps1CardAppend(card,"FULL",raw,sizeof(raw)));
    memmove(card+3904,card,PS1_CARD_SIZE);memcpy(card,"123-456-STD",11);
    assert(ps1CardOffset(card,PS1_CARD_SIZE+3904)==3904);
    assert(ps1CardOffset(card,PS1_CARD_SIZE-1)<0);
    free(card);
    assert(saveArchiveSupported("SAVE.SpS") && saveArchiveSupported("save.MCS") && !saveArchiveSupported("game.ELF"));
    puts("PASS: PSU, CBS, XPS/SPS, MAX, PS1/PS2 PSV, MCS, PSX and raw saves; truncated/mutated containers; PS1 block chains, checksums, full cards and wrapper conversion");
}
'''

with tempfile.TemporaryDirectory(prefix='save-formats-') as folder:
    folder = Path(folder)
    (folder / 'test.c').write_text(code)
    for name, data in fixtures.items():
        (folder / name).write_bytes(data)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    exe = folder / 'test'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', *flags,
                    '-I', str(root / 'include'), str(folder / 'test.c'), str(root / 'src/save_archive.c'),
                    str(root / 'src/save_lzari.c'), str(root / 'src/save_sign.c'), '-lz', '-o', str(exe)], check=True)
    subprocess.run([str(exe), *(str(folder / name) for name in fixtures)], check=True, timeout=60)
