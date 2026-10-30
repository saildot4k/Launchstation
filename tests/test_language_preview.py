"""Run the production language preview and setter with host storage/UI mocks."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
settings = (root / "src/dash_settings.c").read_text()
language = (root / "src/lang.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
enum { LANG_Copy, LANG_Paste, LANG_Cancel, LANG_COUNT };
#define LNG(key) Lang_String[LANG_##key].String
#define BUILTIN_LANGUAGE_COUNT 3
#define DI_CHECK 1
typedef struct { const char *String; } Language;
static Language tables[3][LANG_COUNT] = {
    {{"Copy"},{"Paste"},{"Cancel"}},
    {{"Copier"},{"Coller"},{"Annuler"}},
    {{"Kopieren"},{"Einfuegen"},{"Abbrechen"}}
};
static Language Lang_String[LANG_COUNT];
static struct { int language, unrelated, external; } config, *setting=&config;
static int releases, localized, external_loads, dirty, refreshes;
static int await_ok=1, awaits, menus, result, highlights[4], highlight_count;
static void (*preview)(int);
typedef struct { int icon; const char *label, *detail; int disabled; } DashMenuItem;
static int normalizeBuiltinLanguage(int n) { return n>=0 && n<3 ? n : 0; }
static const Language *getBuiltinLanguageTable(int n) { return tables[normalizeBuiltinLanguage(n)]; }
static void releaseExternalLanguageBuffer(void) { releases++; }
static void updateLocalizedMiscPaths(void) { localized=setting->language; }
'''
code += function(language, "void Set_Language(")
code += r'''
static void Load_External_Language(void) {
    external_loads++;
    if(setting->external) Lang_String[LANG_Copy].String="CUSTOM COPY";
}
static void refreshDirty(int force) {
    assert(force);refreshes++;dirty=setting->language!=0 || setting->unrelated!=42;
}
static int dashWorkerAwaitAll(const char *status) {
    assert(status && *status);awaits++;return await_ok;
}
static void dashModalSetPreview(void (*fn)(int)) { assert(!preview);preview=fn; }
static int dashModalMenu(const char *title,const char *subtitle,
                         const DashMenuItem *items,int n,int initial) {
    assert(!strcmp(title,"Language") && subtitle && n==3 && preview);
    menus++;
    for(int i=0;i<n;i++) {
        assert(items[i].label && !items[i].detail && !items[i].disabled);
        assert(items[i].icon==(i==initial ? DI_CHECK : -1));
    }
    int loads=external_loads;
    void (*callback)(int)=preview;preview=NULL;
    for(int i=0;i<highlight_count;i++) {
        int selected=highlights[i];callback(selected);
        assert(setting->language==selected && localized==selected);
        for(int key=0;key<LANG_COUNT;key++)
            assert(!strcmp(Lang_String[key].String,tables[selected][key].String));
        char expected[128];
        snprintf(expected,sizeof(expected),"%s / %s / %s",LNG(Copy),LNG(Paste),LNG(Cancel));
        assert(!strcmp(subtitle,expected));
        assert(external_loads==loads); /* no device access on highlight */
        refreshDirty(1); /* underlying Settings can update while previewing */
    }
    return result;
}
static char language_preview[128];
'''
code += function(settings, "static void languagePreview(")
code += function(settings, "static int chooseLanguage(")
# Use the same acceptance operations as the real Settings setter.
accepted = re.search(r"case S_LANGUAGE:\s*(.*?)\s*break;",
                     function(settings, "static void setChoice("), re.S).group(1)
code += "static void accept(int v) {\n" + accepted + "\n}\n"
code += r'''
static const char *const names[]={"English","Francais","Deutsch"};
static int choose(void) {
    int chosen=chooseLanguage(names,3,setting->language);
    if(chosen>=0)accept(chosen);
    return chosen;
}
int main(void) {
    setting->unrelated=42;Set_Language(0);
    highlights[0]=0;highlights[1]=1;highlights[2]=2;highlight_count=3;result=2;
    assert(choose()==2 && setting->language==2 && !strcmp(LNG(Copy),"Kopieren"));
    assert(awaits==1 && menus==1 && external_loads==1 && setting->unrelated==42);
    /* A Cancel after several live previews restores both language and
     * external overrides, including the dirty state before opening. */
    Set_Language(0);setting->external=1;Load_External_Language();
    highlights[0]=1;highlights[1]=2;highlight_count=2;result=-1;
    int loads=external_loads, refreshed=refreshes;
    assert(choose()==-1 && setting->language==0 && !strcmp(LNG(Copy),"CUSTOM COPY"));
    assert(external_loads==loads+1 && refreshes==refreshed+3 && !dirty);
    setting->unrelated=99;
    assert(choose()==-1 && dirty && setting->unrelated==99);
    /* Confirm can arrive in the same sample as a move, before the new
     * row's preview callback. The normal setter applies that final row. */
    highlights[0]=0;highlight_count=1;result=1;
    assert(choose()==1 && setting->language==1 && localized==1);
    assert(!strcmp(LNG(Copy),"CUSTOM COPY") && !strcmp(LNG(Paste),"Coller"));
    /* Immediate cancel also restores the existing external table. */
    highlight_count=0;result=-1;
    assert(choose()==-1 && setting->language==1 && !strcmp(LNG(Copy),"CUSTOM COPY"));
    /* Cancelling the storage drain never starts or mutates a preview. */
    await_ok=0;int opened=menus, released=releases;loads=external_loads;
    assert(choose()==-1 && menus==opened && releases==released && external_loads==loads);
    assert(setting->language==1 && setting->unrelated==99 && !preview);
    puts("PASS: live language tables and translated samples, acceptance, Cancel/external restoration, dirty state and storage-drain cancellation");
}
'''
with tempfile.TemporaryDirectory(prefix="language-preview-") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(code)
    compiler = shutil.which("cc") or shutil.which("gcc")
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True)
