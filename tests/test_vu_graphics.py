"""Exercise real scalar kernels and VIF packets; interpret the VU1 source.

The interpreter checks math, memory boundaries, branch delay slots and VF/load
hazards. It is not a substitute for PS2 timing, GIF arbitration or hardware FP.
"""
from pathlib import Path
import ast
import ctypes as C
import math
import os
import random
import re
import struct
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from configure_vu import configure


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def floating(value):
    return struct.unpack('<f', struct.pack('<I', value))[0]


class Tower(C.Structure):
    _fields_ = [(name, C.c_float) for name in ('x', 'y', 'h', 'lum')]


class Camera(C.Structure):
    _fields_ = [(name, C.c_float) for name in ('ca', 'sa', 'cx', 'cy', 'cam_h', 'f', 'half_width', 'floor_h')]


class Projection(C.Structure):
    _fields_ = [(name, C.c_float * 4) for name in ('tx', 'ty', 'bx', 'by')]


class Vertex(C.Structure):
    _fields_ = [('direction', C.c_float * 4), ('color', C.c_uint32 * 4)]


class Screen(C.Structure):
    _fields_ = [(name, C.c_float) for name in ('scale_x', 'scale_y', 'cx', 'cy')]
    _fields_ += [(name, C.c_uint32) for name in ('offset_x', 'offset_y', 'context')]


def unpack_vif(words):
    memory = [[0xdeadbeef] * 4 for _ in range(1024)]
    pc, commands = 0, []
    while pc < len(words):
        code = words[pc]; pc += 1
        cmd = code >> 24
        if cmd == 0:
            assert code == 0
        elif cmd == 0x20:
            assert words[pc] == 0; pc += 1
        elif cmd == 0x6c:
            count = (code >> 16) & 255 or 256
            address = code & 1023
            assert address + count <= 263 and pc % 4 == 0
            for i in range(count):
                memory[address + i] = list(words[pc:pc + 4]); pc += 4
        else:
            commands.append(code)
    assert commands[0:2] == [0x01000101, 0x05000000]
    assert commands[-3:-1] == [0x14000000, 0x13000000]
    assert commands[-1] >> 24 == 7
    assert len(words) % 4 == 0
    return memory


def program():
    code, labels = [], {}
    for line in (root / 'src/dash_vu1_tunnel.vsm').read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(('.', ';', '#')):
            continue
        if line.endswith(':'):
            labels[line[:-1]] = len(code)
        else:
            pair = re.split(r'\s{2,}', line)
            assert len(pair) == 2, line
            code.append(pair)
    return code, labels


def run_vu1(memory):
    code, labels = program()
    vf = [[0] * 4 for _ in range(32)]; vf[0][3] = bits(1)
    vi = [0] * 16
    ready = [0] * 32
    pending, transfers = [], []
    pc = cycle = 0
    branch = end = None

    def vector(register):
        i = int(register[2:])
        assert ready[i] <= cycle, ('VF hazard', register, cycle, ready[i], code[pc])
        return vf[i][:]

    def operands(instruction):
        opcode, *rest = instruction.lower().split(None, 1)
        return opcode, re.split(r',\s*', rest[0]) if rest else []

    def address(value):
        match = re.fullmatch(r'(-?\d+)\(vi(\d+)\)', value)
        assert match, value
        index = int(match[1]) + vi[int(match[2])]
        assert 0 <= index < 1024
        return index

    while cycle < 50000:
        for due, kind, index, mask, values in pending[:]:
            if due <= cycle:
                target = vf[index] if kind == 'vf' else memory[index]
                for lane in mask:
                    target[lane] = values[lane]
                pending.remove((due, kind, index, mask, values))
        old_branch, old_end = branch, end
        branch = end = None
        upper, lower = code[pc]
        opcode, args = operands(upper)
        ending = '[e]' in opcode
        opcode = opcode.replace('[e]', '')
        if opcode != 'nop':
            operation, mask = opcode.split('.')
            lanes = ['xyzw'.index(c) for c in mask]
            target = int(args[0][2:])
            a = [floating(x) for x in vector(args[1])]
            if operation == 'ftoi4':
                values = [int(f32(x * 16)) & 0xffffffff for x in a]
            else:
                broadcast = operation[-1] if args[2][-1] in 'xyzw' else None
                base = operation[:-1] if broadcast else operation
                source = args[2][:-1] if broadcast else args[2]
                b = [floating(x) for x in vector(source)]
                if broadcast:
                    b = [b['xyzw'.index(broadcast)]] * 4
                functions = {'mul': lambda x,y:x*y, 'add':lambda x,y:x+y,
                             'sub':lambda x,y:x-y, 'max':max, 'mini':min}
                values = [bits(f32(functions[base](x,y))) for x,y in zip(a,b)]
            ready[target] = cycle + 4
            pending.append((cycle + 4, 'vf', target, lanes, values))
        opcode, args = operands(lower)
        if opcode == 'lq':
            target = int(args[0][2:]); ready[target] = cycle + 4
            pending.append((cycle + 4, 'vf', target, range(4), memory[address(args[1])][:]))
        elif opcode == 'sq':
            pending.append((cycle + 4, 'mem', address(args[1]), range(4), vector(args[0])))
        elif opcode.startswith('ilw.'):
            vi[int(args[0][2:])] = memory[address(args[1])]['xyzw'.index(opcode[-1])] & 65535
        elif opcode == 'mtir':
            vi[int(args[0][2:])] = vector(args[1][:-1])['xyzw'.index(args[1][-1])] & 65535
        elif opcode in ('iadd', 'iaddiu', 'isubiu'):
            a = vi[int(args[1][2:])]
            b = vi[int(args[2][2:])] if opcode == 'iadd' else int(args[2], 0)
            vi[int(args[0][2:])] = (a-b if opcode == 'isubiu' else a+b) & 65535
        elif opcode.startswith('isw.'):
            values = [vi[int(args[0][2:])]] * 4
            pending.append((cycle + 4, 'mem', address(args[1]), ['xyzw'.index(opcode[-1])], values))
        elif opcode == 'ibne':
            # The source deliberately leaves a gap after changing branch VI.
            assert 'isubiu' not in code[pc-1][1], 'VI branch hazard'
            if vi[int(args[0][2:])] != vi[int(args[1][2:])]:
                branch = labels[args[2]]
        elif opcode == 'xgkick':
            start = vi[int(args[0][2:])]
            assert not any(kind == 'mem' for _,kind,*_ in pending), 'XGKICK reads pending stores'
            transfers.append(start)
        else:
            assert opcode == 'nop', opcode
        if ending:
            end = True
        if old_end:
            break
        pc = old_branch if old_branch is not None else pc + 1
        cycle += 1
    else:
        raise AssertionError('microprogram did not terminate')
    assert transfers == [512]
    return memory


def model_vu0(camera, tower):
    # Execute the actual macro-instruction stream, with macro-mode interlocks.
    source = (root / 'src/dash_vu_math.c').read_text()
    start = source.index('__asm__ volatile(')
    body = source[start:source.index(': : "r"(c)', start)]
    code = ''.join(ast.literal_eval(m[0]) for m in re.finditer(r'"(?:[^"\\]|\\.)*"', body))
    vf = [[0.0]*4 for _ in range(32)];vf[0][3] = 1.0
    memory = {0:list(camera),1:list(tower),2:[0.0]*16,3:[-1,1,-1,1],4:[-1,-1,1,1],5:[1.12,0,0,0]}
    q = 0.0
    for line in code.splitlines():
        args = re.split(r'[ ,]+', line.strip())
        op = args.pop(0)
        if op in ('lqc2','sqc2'):
            match = re.fullmatch(r'(\d+)\(%(\d+)\)',args[1]);assert match
            pos, base = int(match[1])//4,int(match[2]);reg=int(args[0][3:])
            if op=='lqc2':vf[reg]=[f32(v) for v in memory[base][pos:pos+4]]
            else:memory[base][pos:pos+4]=vf[reg]
        elif op=='vdiv':
            assert args[0]=='$Q'
            def component(s):return vf[int(s[3:-1])]['xyzw'.index(s[-1])]
            q=f32(component(args[1])/component(args[2]))
        elif op=='vwaitq':
            pass
        else:
            operation,mask=op[1:].split('.')
            target=int(args[0][3:]);a=vf[int(args[1][3:])][:]
            if operation.endswith('q'):
                base=operation[:-1];b=[q]*4
            elif operation[-1] in 'xyzw':
                base=operation[:-1];b=[vf[int(args[2][3:-1])]['xyzw'.index(args[2][-1])]]*4
            else:base=operation;b=vf[int(args[2][3:])][:]
            functions={'add':lambda x,y:x+y,'sub':lambda x,y:x-y,'mul':lambda x,y:x*y}
            for lane in mask:
                j='xyzw'.index(lane);vf[target][j]=f32(functions[base](a[j],b[j]))
    return memory[2]


with tempfile.TemporaryDirectory(prefix='launchstation-vu-') as temp:
    temp=Path(temp);libpath=temp/'vu.so'
    subprocess.run([os.environ.get('CC','cc'),'-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror',
                    '-I',str(root/'include'),str(root/'src/dash_vu_math.c'),str(root/'src/dash_vu1.c'),'-lm','-o',str(libpath)],check=True)
    lib=C.CDLL(str(libpath))
    lib.dashVuTowerProjectCpu.argtypes=lib.dashVuTowerProject.argtypes=[C.POINTER(Camera),C.POINTER(Tower),C.c_size_t,C.POINTER(Projection)]
    lib.dashVu1BuildPacket.argtypes=[C.POINTER(C.c_uint32),C.c_size_t,C.POINTER(Screen),C.POINTER(Vertex),C.c_uint,C.c_uint]
    lib.dashVu1BuildPacket.restype=C.c_size_t
    rng=random.Random(90210)
    for iteration in range(1200):
        angle=rng.uniform(-7,7)
        camera=Camera(math.cos(angle),math.sin(angle),rng.uniform(280,360),rng.uniform(180,260),rng.uniform(135,165),300,3.7,-40)
        tower=Tower(rng.uniform(-80,80),rng.uniform(-60,60),rng.uniform(8,96),1)
        a,b=Projection(),Projection()
        lib.dashVuTowerProjectCpu(C.byref(camera),C.byref(tower),1,C.byref(a));lib.dashVuTowerProject(C.byref(camera),C.byref(tower),1,C.byref(b))
        got=list(a.tx)+list(a.ty)+list(a.bx)+list(a.by)
        modeled=model_vu0([getattr(camera,n) for n,_ in camera._fields_],[tower.x,tower.y,tower.h,tower.lum])
        for j in range(4):
            x=tower.x+(camera.half_width if j&1 else -camera.half_width)
            y=tower.y+(camera.half_width if j&2 else -camera.half_width)
            rx=x*camera.ca-y*camera.sa;ry=x*camera.sa+y*camera.ca
            for h,xx,yy in [(tower.h,a.tx[j],a.ty[j]),(-40,a.bx[j],a.by[j])]:
                scale=camera.f/(camera.cam_h-h)
                assert abs(xx-(camera.cx+rx*scale*1.12))<0.001
                assert abs(yy-(camera.cy+ry*scale))<0.001
        assert all(abs(x-y)<0.001 for x,y in zip(got,modeled))
        assert bytes(a)==bytes(b)
    print('PASS: 1,200 tower cases match the original projection and actual VU0 instruction math model')

    for quads in (1,2,16,31,32):
        for scale in (1.0,512/448):
            for context in (0,1):
                s=Screen(1.18,scale,320,224*scale,32768,32768,context)
                vertices=(Vertex*(quads*4))()
                for v in vertices:
                    v.direction[:]=[rng.uniform(-2,2),rng.uniform(-2,2),rng.uniform(0,2000),0]
                    v.color[:]=[rng.randrange(256),rng.randrange(256),rng.randrange(256),128]
                words=(C.c_uint32*1092)(*([0xcccccccc]*1092))
                length=lib.dashVu1BuildPacket(words,1088,C.byref(s),vertices,quads,17)
                assert length and all(x==0xcccccccc for x in words[length:])
                memory=run_vu1(unpack_vif(list(words[:length])))
                for q in range(quads):
                    tag=memory[512+q*9]; assert tag[0]==4 and not(tag[0]&0x8000) and tag[2]==0x51
                    assert (tag[1]>>28)==2 and ((tag[1]>>24)&1)==context
                    for j in range(4):
                        v=vertices[q*4+j];color=memory[513+q*9+j*2];xyz=memory[514+q*9+j*2]
                        assert color==list(v.color) and xyz[2:]==[0,0]
                        for lane in (0,1):
                            multiplier=s.scale_x if lane==0 else s.scale_y
                            center=s.cx if lane==0 else s.cy
                            offset=s.offset_x if lane==0 else s.offset_y
                            projected=f32(f32(f32(v.direction[lane]*v.direction[2])*multiplier)+center)
                            expected=max(0,min(65535,int(f32(projected*16))+offset))
                            assert abs(xyz[lane]-expected)<=1,(xyz[lane],expected)
                end=512+quads*9
                assert memory[end]==[32769,1<<28,0xe,0] and memory[end+1]==[0,0,0x61,0]
                assert memory[end+2]==[0xdeadbeef]*4
                before=bytes(words)
                assert not lib.dashVu1BuildPacket(words,length-1,C.byref(s),vertices,quads,17)
                assert bytes(words)==before
                for invalid in (0,33,0xffffffff):
                    assert not lib.dashVu1BuildPacket(words,1088,C.byref(s),vertices,invalid,17)
                for invalid in (0,65536):
                    assert not lib.dashVu1BuildPacket(words,1088,C.byref(s),vertices,quads,invalid)
                vertices[0].direction[0]=float('nan')
                assert not lib.dashVu1BuildPacket(words,1088,C.byref(s),vertices,quads,17)
                vertices[0].direction[0]=0;vertices[0].color[3]=129
                assert not lib.dashVu1BuildPacket(words,1088,C.byref(s),vertices,quads,17)
                assert bytes(words)==before
    print('PASS: real VIF packets and VU1 source execution, 256-qword UNPACK boundary, 32-quad capacity, contexts, PAL scaling, clipping, branch/load/store hazards, colors, EOP/FINISH and invalid-input guards')

    source=(root/'ps2.yaml').read_text()
    for stage in ('profile','vu0','vu1','both','vu1-reference'):
        profile=configure(source,stage)
        assert profile.count('DASH_PROFILE=1')==1 and source not in ('',profile)
        assert 'src/dash_vu1_tunnel.vsm' in profile
        reference = int(stage == 'vu1-reference')
        assert f'DASH_VU1_REFERENCE={reference}' in profile
    assert not re.search(r'^\s+- DASH_VU[01]=1',source,re.M)
    print('PASS: opt-in build profiles; normal builds retain CPU rendering')
