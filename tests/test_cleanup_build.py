"""Execute the retained startup entry and garbage-collect real embedded blobs."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


compiler = shutil.which('gcc') or shutil.which('cc')
assert compiler, 'Host C compiler required'
main = (ROOT/'src/main.c').read_text()
code = r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "main_actions.h"
#define MAX_PATH 1024
#define MAX_NAME 256
enum BOOT_DEVICE {BOOT_DEVICE_TEST=3};
static int boot_argc,cdmode,phase,boot_calls,swapKeys,console_is_PSX;
static int load_error=-1,config_loads;
static struct {int swapKeys;} config,*setting=&config;
static char LaunchElfDir[MAX_PATH]="usb0:/BOOT/",LaunchElfBootDir[MAX_PATH]="usb0:/BOOT/";
#define DPRINTF(...) ((void)0)
#define FALSE 0
#define TRUE 1
static void checkSaveTargets(const char *filename);
static char *boot_argv[8];
static char boot_path[MAX_PATH],mainMsg[MAX_PATH],CNF[MAX_NAME];
static char default_ESR_path[]="mc:/BOOT/ESR.ELF";
static char default_OSDSYS_path[30]="mc:/BOOT/OSDSYS.KELF",default_OSDSYS_path2[30]="mc:/OSDSYS.KELF";
static char rough_region='E',ROMVER_data[16]="0220EC20060210";
static void filerSizeCacheInit(void) {assert(phase++==0);}
'''
code += function((ROOT/'src/main_boot.c').read_text(), 'void captureBootArguments(')
code += r'''
static void Reset(void) {assert(phase++==1);}
static void Init_Default_Language(void) {}
static int wleExists(const char *p) {assert(!strcmp(p,"rom0:PSXVER"));return 0;}
static enum BOOT_DEVICE prepareBootDeviceAndPath(const char *arg,char *path,size_t size) {
 assert(arg==(boot_argc?boot_argv[0]:NULL));snprintf(path,size,"usb0:/BOOT.ELF");return BOOT_DEVICE_TEST;
}
static void bringUpBootDeviceStack(enum BOOT_DEVICE boot) {assert(boot==BOOT_DEVICE_TEST);}
static void initializeBootDisplayDefaults(void) {}
static int loadConfig(char *message,char *filename) {
 assert(message==mainMsg&&!strcmp(filename,"LAUNCHSTATION.CNF"));config_loads++;return load_error;
}
static void uLE_InitializeRegion(void) {strcpy(ROMVER_data,"0220EC20060210");}
static void mapDefaultFileBrowserLaunchKeyToOkButton(void) {}
static void bringUpBootNetworkStack(enum BOOT_DEVICE boot) {assert(boot==BOOT_DEVICE_TEST);}
static void initializeBootGraphics(void) {assert(config_loads);}
'''
code += function((ROOT/'src/main_boot.c').read_text(), 'enum BOOT_DEVICE performEarlyBootInitialization(')
code += r'''
static void initializeRuntimeInputModules(enum BOOT_DEVICE boot) {assert(phase++==2&&boot==BOOT_DEVICE_TEST);}
static void initializeRuntimeDisplayModules(int error,char *message) {assert(phase++==3&&error==load_error&&message==mainMsg);}
static void validateConfiguredCnfPath(void) {assert(phase++==4);}
static void DashRun(const MainExecuteContext *ctx,int from_boot) {
 assert(phase++==5&&from_boot&&cdmode==-1&&ctx->elf_iop_mode==MAIN_ELF_IOP_DEFAULT);
 assert(ctx->boot_argc==boot_argc&&ctx->boot_argv==boot_argv&&ctx->boot_path==boot_path);
 assert(ctx->main_msg==mainMsg&&ctx->cnf_path==CNF&&ctx->rough_region==rough_region);
 assert(ctx->default_esr_path==default_ESR_path&&ctx->default_osdsys_path==default_OSDSYS_path);
 assert(ctx->default_osdsys_path2==default_OSDSYS_path2&&ctx->romver_data==ROMVER_data);
 checkSaveTargets(ctx->cnf_path);boot_calls++;
}
'''
config_source = (ROOT/'src/config.c').read_text()
code += r'''
static int CheckMC(void) {return 1;}
static int configGetPreferredSysconfPort(const char *file,const char *loaded) {
 assert(file&&loaded);return 1;
}
'''
for signature in ('void configAppendPathFile(', 'static void configResolveMcAliasPath(',
                  'static void configBuildSysconfPathForLoaded(', 'static void configBuildSaveTargetsFrom('):
    code += function(config_source, signature)
code += r'''
static void checkSaveTargets(const char *filename) {
 char override[MAX_PATH],cwd[MAX_PATH],sysconf[MAX_PATH];int has_override;
 assert(!strcmp(filename,"LAUNCHSTATION.CNF"));
 const char *folders[]={"mc0:/Config", "mc:/Config/", "usb1:/Config/", "hdd0:/__sysconf/Config"};
 const char *expected[]={"mc0:/Config/LAUNCHSTATION.CNF", "mc1:/Config/LAUNCHSTATION.CNF",
                         "usb1:/Config/LAUNCHSTATION.CNF", "hdd0:/__sysconf/Config/LAUNCHSTATION.CNF"};
 for(unsigned i=0;i<sizeof(folders)/sizeof(*folders);i++) {
  configBuildSaveTargetsFrom(override,sizeof(override),cwd,sizeof(cwd),sysconf,sizeof(sysconf),
                            filename,"usb0:/BOOT/LAUNCHSTATION.CNF",&has_override,folders[i]);
  assert(has_override&&!strcmp(override,expected[i]));
  assert(!strcmp(cwd,"usb0:/BOOT/LAUNCHSTATION.CNF"));
  assert(!strcmp(sysconf,"mc1:/SYS-CONF/LAUNCHSTATION.CNF"));
 }
 configBuildSaveTargetsFrom(override,sizeof(override),cwd,sizeof(cwd),sysconf,sizeof(sysconf),
                           filename,"usb0:/BOOT/LAUNCHSTATION.CNF",&has_override,"");
 assert(!has_override&&!override[0]);
}
'''
code += function(main, 'int main(').replace('int main(', 'static int startup(')
code += r'''
int main(void) {
 char *args[]={"usb0:/BOOT.ELF","one","two","three","four","five","six","seven","eight"};
 for(int count=0;count<=9;count++) {
  phase=0;load_error=count%2?-1:0;memset(boot_argv,0,sizeof(boot_argv));
  assert(startup(count,args)==0&&phase==6);
  for(int i=0;i<count&&i<8;i++)assert(boot_argv[i]==args[i]);
 }
 assert(boot_calls==10&&config_loads==10);
 phase=1;boot_argc=0;
 assert(performEarlyBootInitialization(NULL,boot_path,sizeof(boot_path),mainMsg,NULL,0,NULL)==BOOT_DEVICE_TEST);
 assert(config_loads==11);
 puts("PASS: actual startup entry retains initialization order, arguments, paths, LAUNCHSTATION.CNF load/save targets (including overrides), and default launch policy");
}
'''

with tempfile.TemporaryDirectory(prefix='cleanup-build-') as folder:
    path = Path(folder)
    (path/'startup.c').write_text(code)
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'include'),
                    str(path/'startup.c'), '-o', str(path/'startup')], check=True)
    subprocess.run([str(path/'startup')], check=True, timeout=10)

    # Preprocess the production macros and assemble their actual .incbin files.
    # x86 GAS calls its 32-bit integer directive .long; MIPS calls it .word.
    # Only that spelling changes for this host test; payload sections/symbols,
    # slice offsets, lengths and reference-based retention use production code.
    source = ROOT/'src/embed_blobs.S'
    asm = subprocess.check_output([compiler, '-E', '-P', '-x', 'assembler-with-cpp', str(source)],
                                  cwd=ROOT, text=True)
    (path/'blobs.s').write_text(asm.replace('.word ', '.long '))
    subprocess.run([compiler, '-c', str(path/'blobs.s'), '-o', str(path/'blobs.o')], cwd=ROOT, check=True)
    payloads = re.findall(r'^EMBED_(?:FILE|SLICE|TAIL)\((\w+),', source.read_text(), re.M)
    nm = shutil.which('nm')
    assert nm, 'Host nm required'
    for referenced in ('data', 'size'):
        expression = "sfx_cursor_adp[0]=='A'" if referenced=='data' else f'size_sfx_cursor_adp=={(ROOT/"res/sfx/cursor.adp").stat().st_size}'
        (path/'root.c').write_text('extern const unsigned char sfx_cursor_adp[];\n'
                                  'extern const unsigned int size_sfx_cursor_adp;\n'
                                  f'int main(void){{return !({expression});}}\n')
        binary = path/referenced
        subprocess.run([compiler, '-ffunction-sections', '-fdata-sections', '-no-pie',
                        '-Wl,--gc-sections', '-Wl,-z,noexecstack', str(path/'root.c'),
                        str(path/'blobs.o'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=10)
        names = {line.split()[-1] for line in subprocess.check_output([nm, '--defined-only', str(binary)], text=True).splitlines() if line.split()}
        for name in payloads:
            assert (name in names) == (name=='sfx_cursor_adp'), (referenced,name)
            assert ('size_'+name in names) == (name=='sfx_cursor_adp'), (referenced,name)
    print('PASS: production blob sections keep payload/size pairs when either is referenced and discard every unreferenced payload')

# Both maintained build paths must omit removed modules/assets and retain the
# old section numbers, so existing saved Devices destinations still mean Files.
make = (ROOT/'Makefile').read_text()
project = (ROOT/'ps2.yaml').read_text()
shell = (ROOT/'src/dash_main.c').read_text()
store = (ROOT/'src/dash_store.c').read_text()
header = (ROOT/'include/dash_internal.h').read_text()
for name in ('main_menu','dash_files','sfx_boot_adp'):
    assert name+'.o' not in make
    assert 'src/'+name+'.c' not in project
for name in ('src/main_menu.c','include/main_menu.h','src/dash_files.c','res/sfx/boot.adp'):
    assert not (ROOT/name).exists()
assert '-ffunction-sections -fdata-sections' in make and '--gc-sections' in make
assert '      - -fdata-sections' in project
assert 'DASH_SEC_DEVICES' in header and 'if (s == DASH_SEC_DEVICES)\n\t\ts = DASH_SEC_FILES;' in shell
assert '&dashFilesScreen, &dashFilesScreen,' in shell
assert 'files_mode' not in header and 'Dash_FilesMode' not in store
assert 'sfx_boot_adp' not in (ROOT/'src/embed_blobs.S').read_text()+(ROOT/'embed.make').read_text()
assert 'dashSoundRequestBoot' not in (ROOT/'src/dash_sound.c').read_text()
print('PASS: both build definitions exclude obsolete code/assets and preserve saved section IDs')
