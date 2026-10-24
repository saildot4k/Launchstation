"""Execute Neutrino's MMCE-before-loader order, MX4SIO exclusion and fallback."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/neutrino_iso.c").read_text()
start = source.index("static int prepareNeutrinoCandidateLaunch(")
end = source.index("\n}\n", start) + 3

code = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 256
#define POPSTARTER_OK 1
#define POPSTARTER_ERR_OPEN_POPSTARTER -1
typedef struct { char path[MAX_PATH]; } Candidate;
typedef struct { Candidate entry[2]; int count; } POPSTARTER_CANDIDATE_LIST;
static int loads, prepares, load_ok, mx_active, results[2], wanted_loads[2];
#ifdef MMCE
static int loadMmceModules(void) {
 loads++;if(load_ok)mx_active=0;return load_ok;
}
#endif
static int preparePopstarterElfLaunch(const char *path,char *full,size_t full_size,
                                     char *party,size_t party_size,int *kind) {
 assert(loads==wanted_loads[prepares]); /* MMCE entry precedes loader IO. */
 snprintf(full,full_size,"%s",path);(void)party_size;party[0]=0;*kind=1;
 return results[prepares++];
}
""" + source[start:end] + r"""
static void reset(void) {
 loads=prepares=0;load_ok=1;mx_active=1;
 results[0]=results[1]=POPSTARTER_OK;wanted_loads[0]=wanted_loads[1]=0;
}
static int wantsMmce(const char *iso,const char *elf) {
#ifdef MMCE
 return strncmp(iso,"mx4sio",6) && strncmp(elf,"mx4sio",6);
#else
 (void)iso;(void)elf;return 0;
#endif
}
int main(void) {
 const char *isos[]={"usb1:/GAME.ISO","mass:/GAME.ISO","mass3:/GAME.ISO",
                     "ata0:/GAME.ISO","ata1:/GAME.ISO","mmce0:/GAME.ISO",
                     "udpfs:/GAME.ISO","mx4sio:/GAME.ISO","mx4sio0:/GAME.ISO"};
 const char *elfs[]={"usb0:/N.ELF","mc0:/N.ELF","ata0:/N.ELF","mx4sio:/N.ELF","mx4sio0:/N.ELF"};
 char selected[MAX_PATH],full[MAX_PATH],party[MAX_PATH];int kind;
 POPSTARTER_CANDIDATE_LIST candidates={0};candidates.count=1;
 for(unsigned i=0;i<sizeof(isos)/sizeof(*isos);i++)
  for(unsigned j=0;j<sizeof(elfs)/sizeof(*elfs);j++)
   for(int present=0;present<2;present++) {
    reset();load_ok=present;wanted_loads[0]=wantsMmce(isos[i],elfs[j]);
    snprintf(candidates.entry[0].path,MAX_PATH,"%s",elfs[j]);
    assert(prepareNeutrinoCandidateLaunch(&candidates,isos[i],selected,sizeof(selected),
           full,sizeof(full),party,sizeof(party),&kind)==POPSTARTER_OK);
    assert(prepares==1 && loads==wanted_loads[0]);
    assert(mx_active==!(present && wanted_loads[0]));
    assert(!strcmp(selected,elfs[j]) && !strcmp(full,elfs[j]) && kind==1);
   }
 /* An unavailable configured MX4SIO loader may fall back to a memory card.
  * Initialize MMCE for the actual candidate before preparing that ELF. */
 reset();candidates.count=2;results[0]=POPSTARTER_ERR_OPEN_POPSTARTER;
 strcpy(candidates.entry[0].path,"mx4sio:/MISSING.ELF");
 strcpy(candidates.entry[1].path,"mc1:/N.ELF");
 wanted_loads[1]=wantsMmce("usb0:/GAME.ISO",candidates.entry[1].path);
 assert(prepareNeutrinoCandidateLaunch(&candidates,"usb0:/GAME.ISO",selected,sizeof(selected),
        full,sizeof(full),party,sizeof(party),&kind)==POPSTARTER_OK);
 assert(prepares==2 && loads==wanted_loads[1] && !strcmp(selected,"mc1:/N.ELF"));
 /* Malformed loader stops fallback, matching the shared ELF preparer. */
 reset();results[0]=-2;
 assert(prepareNeutrinoCandidateLaunch(&candidates,"usb0:/GAME.ISO",selected,sizeof(selected),
        full,sizeof(full),party,sizeof(party),&kind)==-2 && prepares==1 && !loads);
 return 0;
}
"""
launch = source[source.index("int LaunchNeutrinoIso("):]
assert launch.index("showNeutrinoLaunchOptions(&options)") < launch.index("ret = prepareNeutrinoCandidateLaunch(")
assert launch.index("ret = prepareNeutrinoCandidateLaunch(") < launch.index("setNeutrinoMmceGameID(")
assert "setNeutrinoMmceGameID(gameID, opened_iso, fullpath);" in launch
cc = shutil.which("gcc") or shutil.which("cc")
assert cc, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="neutrino-mmce-launch-") as folder:
    p = Path(folder)
    (p / "test.c").write_text(code)
    for mmce in (False, True):
        exe = p / ("mmce" if mmce else "no-mmce")
        subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror",
                        *(["-DMMCE"] if mmce else []), str(p / "test.c"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)
print("PASS: MMCE initializes before Neutrino ELF IO, skips MX4SIO sources/loaders, tolerates absent hardware and follows candidate fallback")
