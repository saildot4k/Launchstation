"""Execute real Neutrino discovery and handoff with counted filesystem probes."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/neutrino_iso.c").read_text()
paths = (root / "src/popstarter_path.c").read_text()
internal = (root / "src/popstarter_internal.h").read_text()


def function(text, signature):
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gui_neutrino.h"
#define MAX_PATH 256
#define NEUTRINO_GAME_ID_SIZE 12
'''
code += internal[internal.index("enum POPSTARTER_RESULT"):internal.index("void initPopstarterCandidates(")]
code += r'''
static struct { int disable_neutrino,cdrom_disable_gameid;char neutrino_file[MAX_PATH]; } config,*setting=&config;
typedef struct { char path[MAX_PATH];int magic; } File;
typedef struct { char path[MAX_PATH],resolved[MAX_PATH];int result; } Install;
static File files[32];static Install installs[8];
static int nfiles,ninstalls,probes,prepares,loads,expected_loads,load_ok;
static int validations,iso_ok,ids,options_calls,accept,cleanup,cleanup_ok,runs,signals,mmce_calls;
static int switch_ok,preparing_messages,starting_messages;
static char probe_paths[128][MAX_PATH],iso_path[MAX_PATH],args[1400],prepared[MAX_PATH],switched_loader[MAX_PATH];
static void addFile(const char *path,int magic) {
    assert(nfiles<32);snprintf(files[nfiles].path,MAX_PATH,"%s",path);files[nfiles++].magic=magic;
}
static void install(const char *path,int magic,int result,const char *resolved) {
    assert(ninstalls<8);Install *i=&installs[ninstalls++];
    snprintf(i->path,MAX_PATH,"%s",path);snprintf(i->resolved,MAX_PATH,"%s",resolved?resolved:path);i->result=result;
    addFile(path,magic);
}
static int genCmpFileExt(const char *path,const char *ext) {
    const char *dot=strrchr(path,'.');return dot && !strcmp(dot+1,ext);
}
static int openPathForRead(const char *path,char *opened,size_t size) {
    /* Discovery only probes ELF files, after the user accepts the menu. */
    assert(!strstr(path,".toml"));
    assert(options_calls==1 && accept && probes<128);
    snprintf(probe_paths[probes++],MAX_PATH,"%s",path);
    for(int i=0;i<nfiles;i++)if(!strcmp(path,files[i].path)) {
        if(opened && size)snprintf(opened,size,"%s",path);
        return i+1;
    }
    return -1;
}
static int genRead(int fd,void *buffer,int size) {
    assert(fd>0 && fd<=nfiles && size==4);
    memcpy(buffer,files[fd-1].magic?"\177ELF":"BAD!",4);return 4;
}
static void genClose(int fd) { assert(fd>0 && fd<=nfiles); }
static int validateIso(const char *path,char *opened,size_t size) {
    validations++;assert(!probes);snprintf(opened,size,"%s",path);return iso_ok;
}
static int DashIsActive(void) { return 1; }
static int prepareNeutrinoGameID(const char *path,char *id,size_t size) {
    assert(!strcmp(path,iso_path) && !probes && !options_calls);ids++;snprintf(id,size,"SLUS_123.45");return 1;
}
int showNeutrinoLaunchOptions(NEUTRINO_LAUNCH_OPTIONS *options) {
    assert(!probes && !loads && ids==1);options_calls++;memset(options,0,sizeof(*options));options->game_compatibility=2;return accept;
}
int showNeutrinoLaunchOptionsForGame(NEUTRINO_LAUNCH_OPTIONS *options,const char *id) {
    assert(!strcmp(id,"SLUS_123.45"));return showNeutrinoLaunchOptions(options);
}
int buildNeutrinoOptionArgs(const NEUTRINO_LAUNCH_OPTIONS *options,NEUTRINO_OPTION_ARGS *out) {
    assert(options->game_compatibility==2);strcpy(out->game_arg,"-gc=2");out->argv[0]=out->game_arg;return 1;
}
static int LaunchArgsLoadFromBuffer(const char *title,const char *text,int len,char *message,size_t size) {
    (void)message;(void)size;assert(!strcmp(title,"Neutrino ISO") && len==(int)strlen(text));
    snprintf(args,sizeof(args),"%s",text);return 1;
}
#ifdef MMCE
static int loadMmceModules(void) { loads++;return load_ok; }
static int setNeutrinoMmceGameID(const char *id,const char *iso,const char *elf) {
    assert(!strcmp(id,"SLUS_123.45") && !strcmp(iso,iso_path) && !cleanup && prepares);
    assert(!strcmp(elf,prepared));snprintf(switched_loader,sizeof(switched_loader),"%s",elf);mmce_calls++;return switch_ok;
}
#endif
static int preparePopstarterElfLaunch(const char *path,char *full,size_t full_size,
                                     char *party,size_t party_size,int *kind) {
    (void)party_size;
#ifdef MMCE
    if(strncmp(iso_path,"mx4sio",6) && strncmp(path,"mx4sio",6))expected_loads++;
#endif
    assert(loads==expected_loads);prepares++;
    for(int i=0;i<ninstalls;i++)if(!strcmp(path,installs[i].path)) {
        snprintf(full,full_size,"%s",installs[i].resolved);snprintf(prepared,sizeof(prepared),"%s",full);
        party[0]=0;*kind=1;return installs[i].result;
    }
    assert(!"preparing an unknown installation");return POPSTARTER_ERR_OPEN_POPSTARTER;
}
static void drawMsg(const char *message) {
    assert(setting && !cleanup);
    if(!strcmp(message,"Preparing Neutrino executable..."))preparing_messages++;
    else { assert(!strcmp(message,"Starting Neutrino...") && args[0]);starting_messages++; }
}
static int CleanUpForKeepIopExec(const char *title) {
    assert(!strcmp(title,"Preparing Neutrino") && args[0]);cleanup++;
#ifdef MMCE
    assert(mmce_calls==1 && !strcmp(switched_loader,prepared));
#endif
    if(cleanup_ok)setting=NULL; /* Actual cleanup frees the settings object. */
    return cleanup_ok;
}
static void displayRetroGemGameID(const char *id,int frames) {
    assert(!strcmp(id,"SLUS_123.45") && frames==2 && cleanup==1);signals++;
}
static void RunLoaderElfKeepIOP(char *full,char *party,char *selected,int kind) {
    assert(cleanup==1 && cleanup_ok && signals==!config.cdrom_disable_gameid && kind==1 && !party[0]);
    assert(!strcmp(full,prepared));assert(strstr(args,"-qb\n") && strstr(args,"-gc=2\n"));
    assert(strstr(args,iso_path) && strstr(args,"-cwd="));
    for(int i=0;i<ninstalls;i++)if(!strcmp(selected,installs[i].path)) { runs++;return; }
    assert(!"launching an unknown installation");
}
'''
for signature in ("void initPopstarterCandidates(", "int addPopstarterCandidate("):
    code += function(paths, signature)
for signature in ("static void setMessage(", "int IsNeutrinoIsoPath(",
                  "static int neutrinoElfReadable(",
                  "static int addNeutrinoCandidate(", "static int findNeutrinoOnRoot(",
                  "static int deviceRootCandidate(", "static const char *neutrinoBsdForPath(",
                  "static int buildArgs(", "static int prepareNeutrinoCandidateLaunch(",
                  "int LaunchNeutrinoIso("):
    code += function(source, signature)
code += r'''
static void reset(void) {
    setting=&config;memset(&config,0,sizeof(config));nfiles=ninstalls=probes=prepares=loads=expected_loads=0;
    validations=ids=options_calls=cleanup=runs=signals=mmce_calls=0;
    preparing_messages=starting_messages=0;switch_ok=1;
    accept=iso_ok=cleanup_ok=load_ok=1;args[0]=prepared[0]=switched_loader[0]=0;
    strcpy(iso_path,"usb1:/DVD/GAME.ISO");
}
static int prefixProbes(const char *prefix) {
    int count=0;for(int i=0;i<probes;i++)count+=!strncmp(probe_paths[i],prefix,strlen(prefix));return count;
}
static void success(const char *wanted) {
    char message[512]={0};assert(LaunchNeutrinoIso(iso_path,message,sizeof(message))==1);
    assert(!message[0] && runs==1 && cleanup==1 && ids==1 && options_calls==1 && validations==1);
    assert(!strcmp(prepared,wanted) && preparing_messages==prepares && starting_messages==1);
}
int main(void) {
    /* A valid ELF alone is enough on every device, including mc: aliases
     * resolved to a slot. No configuration or unrelated device is probed. */
    const char *configured[]={"usb0:/Custom/neutrino.elf","ata0:/Custom/neutrino.elf",
        "udpfs:/Custom/neutrino.elf","mmce0:/Custom/neutrino.elf","mx4sio:/Custom/neutrino.elf",
        "mc0:/Custom/neutrino.elf","mc1:/Custom/neutrino.elf","mc:/Custom/neutrino.elf"};
    for(unsigned i=0;i<sizeof(configured)/sizeof(*configured);i++)
    for(int present=0;present<2;present++) {
        reset();load_ok=present;strcpy(config.neutrino_file,configured[i]);
        const char *resolved=i==7?"mc1:/Custom/neutrino.elf":configured[i];
        install(configured[i],1,POPSTARTER_OK,resolved);success(resolved);
        assert(prepares==1 && probes==1);
        for(int p=0;p<probes;p++)assert(!strncmp(probe_paths[p],configured[i],strrchr(configured[i],'/')-configured[i]+1));
    }
    /* Empty, missing and corrupt explicit paths fall back to
     * the game device, without examining either memory-card slot. */
    for(int bad=0;bad<3;bad++) {
        reset();
        if(bad)strcpy(config.neutrino_file,"usb0:/Custom/neutrino.elf");
        if(bad==2)install(config.neutrino_file,0,POPSTARTER_OK,NULL);
        install("usb1:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
        install("mc0:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
        success("usb1:/NEUTRINO/neutrino.elf");assert(prepares==1 && !prefixProbes("mc"));
    }
    /* A path may validate yet fail preparation after driver initialization.
     * Both open failures and invalid executables must allow the next location. */
    const int errors[]={POPSTARTER_ERR_OPEN_POPSTARTER,POPSTARTER_ERR_INVALID_POPSTARTER};
    for(int error=0;error<2;error++) {
        reset();strcpy(config.neutrino_file,"usb0:/Custom/neutrino.elf");
        install(config.neutrino_file,1,errors[error],NULL);
        install("usb1:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
        success("usb1:/NEUTRINO/neutrino.elf");assert(prepares==2 && !prefixProbes("mc"));
    }
    reset();strcpy(config.neutrino_file,"usb0:/Custom/neutrino.elf");
    install(config.neutrino_file,1,POPSTARTER_ERR_OPEN_POPSTARTER,NULL);
    install("usb1:/NEUTRINO/neutrino.elf",1,POPSTARTER_ERR_INVALID_POPSTARTER,NULL);
    install("mc0:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
    install("mc1:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
    success("mc0:/NEUTRINO/neutrino.elf");assert(prepares==3 && !prefixProbes("mc1:"));
    /* Retain all case variants and mc0-before-mc1 order with ELF-only fixtures. */
    const char *variants[]={"mc1:/NEUTRINO/neutrino.elf","mc1:/neutrino/neutrino.elf",
        "mc1:/NEUTRINO/NEUTRINO.ELF","mc1:/neutrino/NEUTRINO.ELF"};
    for(int i=0;i<4;i++) {
        reset();install(variants[i],1,POPSTARTER_OK,NULL);success(variants[i]);
        assert(prefixProbes("usb1:")==4 && prefixProbes("mc0:")==4 && prepares==1);
    }
    char message[512];
#ifdef MMCE
    /* ATA ISO, configured MMCE ELF: failed readiness never starts cleanup or
     * invokes the loader, and must not trigger unrelated fallback discovery. */
    reset();strcpy(iso_path,"ata0:/DVD/GAME.ISO");switch_ok=0;
    strcpy(config.neutrino_file,"mmce0:/Custom/neutrino.elf");
    install(config.neutrino_file,1,POPSTARTER_OK,NULL);
    assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(strstr(message,"MMCE game-card switch") && mmce_calls==1 && args[0]);
    assert(probes==1 && prepares==1 && !cleanup && !runs && !starting_messages && setting);
#endif
    reset();config.cdrom_disable_gameid=1;
    install("usb1:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
    success("usb1:/NEUTRINO/neutrino.elf");assert(!signals && !setting);
    reset();cleanup_ok=0;
    install("usb1:/NEUTRINO/neutrino.elf",1,POPSTARTER_OK,NULL);
    assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)) && cleanup==1 && !runs && !signals && setting);
    reset();assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(strstr(message,"Neutrino not found") && probes==12 && !prepares && !loads && !cleanup && !runs);
    reset();strcpy(config.neutrino_file,"usb0:/Custom/neutrino.elf");
    install(config.neutrino_file,1,POPSTARTER_ERR_INVALID_POPSTARTER,NULL);
    assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(strstr(message,"could not be prepared") && !cleanup && !runs);
    reset();accept=0;assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(!message[0] && !probes && !loads && !prepares && !cleanup);
    reset();iso_ok=0;assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(!ids && !options_calls && !probes);
    reset();config.disable_neutrino=1;assert(!LaunchNeutrinoIso(iso_path,message,sizeof(message)));
    assert(!validations && !ids && !options_calls && !probes);
    puts("PASS: configured Neutrino skips every fallback probe; lazy game-device/mc0/mc1 fallback, preparation failures, aliases, case variants, no TOML probes, cancellation and unchanged MMCE-before-ELF/argument handoff");
}
'''
compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("A host C compiler is required")
with tempfile.TemporaryDirectory(prefix="neutrino-discovery-") as directory:
    c_file = Path(directory) / "discovery.c"
    c_file.write_text(code)
    for mmce in (False, True):
        executable = Path(directory) / ("mmce" if mmce else "no-mmce")
        subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                        *(["-DMMCE"] if mmce else []), "-I", str(root / "include"),
                        str(c_file), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True, timeout=10)
