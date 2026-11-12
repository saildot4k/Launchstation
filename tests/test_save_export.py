"""Production PSU/MCS/PSX/PSV writers, checked against independent layout/crypto oracles."""
from pathlib import Path
import hashlib
import hmac
import os
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
#include "save_archive.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void output(SaveArchive *save,int format,const char *path) {
    uint8_t *data=NULL;size_t length;SaveArchive parsed;
    assert(saveArchiveBuild(save,format,&data,&length));
    assert(saveArchiveParse(&parsed,data,length,path)&&parsed.ps1==save->ps1&&parsed.count==save->count);
    for(unsigned i=0;i<parsed.count;i++) {
        assert(!strcmp(parsed.files[i].name,save->files[i].name));
        assert(parsed.files[i].size==save->files[i].size);
        if(parsed.files[i].size)assert(!memcmp(parsed.files[i].data,save->files[i].data,parsed.files[i].size));
        if(!save->ps1)assert(parsed.files[i].mode==save->files[i].mode&&!memcmp(parsed.files[i].created,save->files[i].created,8));
    }
    if(!save->ps1)assert(!strcmp(parsed.folder.name,save->folder.name)&&!memcmp(parsed.folder.modified,save->folder.modified,8));
    FILE *f=fopen(path,"wb");assert(f&&fwrite(data,1,length,f)==length&&!fclose(f));
    saveArchiveFree(&parsed);free(data);
}
int main(int argc,char **argv) {
    assert(argc==2&&!chdir(argv[1]));
    uint8_t ps1[15*8192],iconsys[964]={0},icon[257],payload[1235];
    for(unsigned i=0;i<sizeof(ps1);i++)ps1[i]=(i*19+(i>>8))&255;
    memcpy(ps1,"SC",2);
    for(unsigned i=0;i<sizeof(icon);i++)icon[i]=(i*13)&255;
    for(unsigned i=0;i<sizeof(payload);i++)payload[i]=(i*7+9)&255;
    SaveArchiveEntry one={0};strcpy(one.name,"BASLUS-12345SAVE");one.mode=0x8497;one.data=ps1;one.size=3*8192;
    SaveArchive save={0};save.ps1=1;save.files=&one;save.count=1;
    output(&save,SAVE_OUTPUT_MCS,"ps1.mcs");output(&save,SAVE_OUTPUT_PSV,"ps1.psv");
    output(&save,SAVE_OUTPUT_PSX,"ps1.psx");
    char psx_name[80];assert(saveArchiveFilename(&save,SAVE_OUTPUT_PSX,psx_name,sizeof(psx_name))&&!strcmp(psx_name,"BASLUS-12345SAVE.psx"));
    strcpy(one.name,"BASLUS-12345SAVEABCD");assert(strlen(one.name)==20);output(&save,SAVE_OUTPUT_PSX,"name20.psx");
    strcpy(one.name,"QUICK-SAVE");output(&save,SAVE_OUTPUT_PSX,"starts-q.psx");
    strcpy(one.name,"BASLUS-12345SAVE");
    one.size=8192;output(&save,SAVE_OUTPUT_PSX,"single.psx");
    one.size=sizeof(ps1);output(&save,SAVE_OUTPUT_PSX,"full.psx");one.size=3*8192;
    char name[80];assert(saveArchiveFilename(&save,SAVE_OUTPUT_PSV,name,sizeof(name))&&!strcmp(name,"BASLUS-1234553415645.PSV"));
    assert(!saveArchiveFilename(&save,SAVE_OUTPUT_PSV,name,8));
    uint8_t *bad=(void*)1;size_t n=123;
    assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSU,&bad,&n)&&!bad&&!n);
    one.size--;assert(!saveArchiveBuild(&save,SAVE_OUTPUT_MCS,&bad,&n));one.size++;
    one.size--;assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSX,&bad,&n));one.size++;
    assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSX+1,&bad,&n));
    memcpy(iconsys,"PS2D",4);strcpy((char*)iconsys+260,"icon.icn");
    // Empty Copy/Delete references use the view icon.
    SaveArchiveEntry files[4]={0};const char *names[]={"icon.sys","icon.icn","data.bin","empty"};
    const uint8_t *contents[]={iconsys,icon,payload,NULL};size_t sizes[]={sizeof(iconsys),sizeof(icon),sizeof(payload),0};
    for(int i=0;i<4;i++) {
        strcpy(files[i].name,names[i]);files[i].mode=0x8497;files[i].data=contents[i];files[i].size=sizes[i];
        for(int j=0;j<8;j++){files[i].created[j]=j+i;files[i].modified[j]=j+i+32;}
    }
    save.ps1=0;save.files=files;save.count=4;strcpy(save.folder.name,"BASLUS-12345SAVE");save.folder.mode=0x8427;
    for(int i=0;i<8;i++){save.folder.created[i]=i+64;save.folder.modified[i]=i+96;}
    output(&save,SAVE_OUTPUT_PSU,"ps2.psu");output(&save,SAVE_OUTPUT_PSV,"ps2.psv");
    assert(!saveArchiveBuild(&save,SAVE_OUTPUT_MCS,&bad,&n));
    assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSX,&bad,&n));
    strcpy((char*)iconsys+324,"missing.icn");assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSV,&bad,&n));iconsys[324]=0;
    strcpy(files[2].name,"icon.icn");assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSU,&bad,&n));strcpy(files[2].name,"../data");
    assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSV,&bad,&n));strcpy(files[2].name,"data.bin");
    files[2].size=SAVE_ARCHIVE_LIMIT;assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSU,&bad,&n));files[2].size=sizeof(payload);
    save.folder.mode=0x8497;assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSU,&bad,&n));
    save.count=SAVE_ARCHIVE_FILES+1;assert(!saveArchiveBuild(&save,SAVE_OUTPUT_PSU,&bad,&n));
    puts("PASS: PS1 MCS/PSX/PSV and PS2 PSU/PSV round trips, one/multiple/fifteen PS1 blocks, 20-byte and Q-prefixed names, metadata, empty files and bounds");
}
'''

def aes(data, key, mode, iv=None):
    command = ['openssl', 'enc', '-aes-128-'+mode, '-d', '-K', key, '-nopad', '-nosalt']
    if iv:
        command += ['-iv', iv]
    return subprocess.run(command, input=data, stdout=subprocess.PIPE, check=True).stdout

with tempfile.TemporaryDirectory(prefix='save-export-') as temp:
    temp = Path(temp)
    (temp/'test.c').write_text(code)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC','cc'), '-std=c99', '-Wall', '-Wextra', '-Werror', *flags,
                    '-I', str(root/'include'), str(temp/'test.c'), str(root/'src/save_archive.c'),
                    str(root/'src/save_sign.c'), str(root/'src/save_lzari.c'), '-lz', '-o', str(temp/'test')], check=True)
    subprocess.run([str(temp/'test'), str(temp)], check=True, timeout=20)
    u32 = lambda data, offset: struct.unpack_from('<I', data, offset)[0]
    for kind in [1,2]:
        data = (temp/f'ps{kind}.psv').read_bytes()
        assert data[:8] == b'\0VSP'+bytes(4) and u32(data,60)==kind
        assert u32(data,56)==(20 if kind==1 else 44)
        seed=data[8:28]
        iv='b30ffeedb7dc5eb7133da60d1b6b2cdc'
        if kind==1:
            key='ab5abc9fc1f49de6a051dbaefa518859'
            decrypted=aes(seed[:16],key,'ecb')
            encrypted=subprocess.run(['openssl','enc','-aes-128-ecb','-e','-K',key,'-nopad','-nosalt'],
                                     input=seed[:16],stdout=subprocess.PIPE,check=True).stdout
            salt=bytes(a^b for a,b in zip(decrypted,bytes.fromhex(iv)))
            salt+=bytes(a^b for a,b in zip(encrypted[:4],seed[16:20]))
            assert u32(data,64)==24576 and u32(data,68)==132 and u32(data,72)==512
            assert u32(data,92)==24576 and u32(data,96)==0x9003
            assert data[100:120].rstrip(b'\0')==b'BASLUS-12345SAVE'
            assert len(data)==132+24576 and data[132:134]==b'SC'
        else:
            salt=aes(seed+bytes(44),'ea02ceef5bb4d2998f611910d77f51c6','cbc',iv)[:20]
            assert u32(data,100)==4 and u32(data,120)==6
            assert data[104:112]==bytes(range(64,72)) and data[112:120]==bytes(range(96,104))
            assert data[128:160].rstrip(b'\0')==b'BASLUS-12345SAVE'
            positions={}
            for index, (name, size) in enumerate([(b'icon.sys',964),(b'icon.icn',257),(b'data.bin',1235),(b'empty',0)]):
                off=168+index*68
                assert data[off+24:off+56].rstrip(b'\0')==name and u32(data,off+16)==size
                assert data[off:off+8]==bytes(range(index,index+8)) and u32(data,off+20)==0x8497
                positions[name]=(u32(data,off+64),size)
            assert (u32(data,68),u32(data,72))==positions[b'icon.sys']
            for off in [76,84,92]:
                assert (u32(data,off),u32(data,off+4))==positions[b'icon.icn']
        unsigned=data[:28]+bytes(20)+data[48:]
        assert hmac.digest(salt,unsigned,hashlib.sha1)==data[28:48], f'PS{kind} signature mismatch'
    mcs=(temp/'ps1.mcs').read_bytes()
    assert len(mcs)==128+24576 and mcs[0]==0x51 and u32(mcs,4)==24576 and mcs[8:10]==b'\xff\xff'
    checksum=0
    for b in mcs[:127]:
        checksum^=b
    assert mcs[127]==checksum
    # Apollo Action Replay PSX: twenty-byte name, 34 zero bytes, raw save.
    for name, game, blocks in [('ps1.psx',b'BASLUS-12345SAVE',3),
                               ('name20.psx',b'BASLUS-12345SAVEABCD',3),
                               ('starts-q.psx',b'QUICK-SAVE',3),
                               ('single.psx',b'BASLUS-12345SAVE',1),
                               ('full.psx',b'BASLUS-12345SAVE',15)]:
        psx=(temp/name).read_bytes()
        raw=bytearray((i*19+(i>>8))&255 for i in range(blocks*8192))
        raw[:2]=b'SC'
        assert len(psx)==54+len(raw)
        assert psx==game.ljust(54,b'\0')+raw, f'{name}: Action Replay layout or payload mismatch'
    assert (temp/'ps2.psu').stat().st_size==1536+4*512+1024+1024+2048
    print('PASS: independent PSX header/payload layouts, PSV signatures/icon offsets, MCS checksum and PSU alignment')
