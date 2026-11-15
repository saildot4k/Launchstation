#include "dash_internal.h"
#include "dash_settings_theme.h"

static DashTheme preview_saved;
static int preview_saved_preset, preview_saved_custom;

static void presetPreview(int index)
{
	dashThemeSetPreset(index);
}

int dashSettingsChoosePreset(void)
{
	DashMenuItem items[32];
	int n = dashThemePresetCount(), i, r;

	if (n > 32)
		n = 32;
	for (i = 0; i < n; i++) {
		items[i].icon = (i == dashThemeBasePreset() && !dashThemeIsCustom()) ? DI_CHECK : -1;
		items[i].label = dashThemePresetInfo(i)->name;
		items[i].detail = NULL;
		items[i].disabled = 0;
	}
	preview_saved = dashTheme;
	preview_saved_preset = dashThemeBasePreset();
	preview_saved_custom = dashThemeIsCustom();
	dashModalSetPreview(presetPreview);
	r = dashModalMenu("Theme", "Move to preview, confirm to keep", items, n, dashThemeBasePreset());
	if (r < 0) {
		dashThemeRestore(&preview_saved, preview_saved_preset, preview_saved_custom);
		return 0;
	}
	dashThemeSetPreset(r);
	return 1;
}

/* Theme folder IO runs on the background worker; the UI waits with a
 * cancellable overlay and applies the result. */
enum {
	TIO_LIST = 0,
	TIO_READ,
	TIO_WRITE
};

typedef struct
{
	int op;
	char folder[DASH_THEME_NAME_MAX];
	char names[24][DASH_THEME_NAME_MAX];
	int n;
	DashTheme t;
	char *text;
	int len;
	int ret;
	int abandoned;
} ThemeIoJob;

static void themeIoRun(void *arg)
{
	ThemeIoJob *j = (ThemeIoJob *)arg;

	if (j->op == TIO_LIST)
		j->n = dashThemeFolderList(j->names, 24);
	else if (j->op == TIO_READ)
		j->ret = dashThemeFolderRead(j->folder, &j->t);
	else
		j->ret = dashThemeFolderWrite(j->folder, j->text, j->len);
}

static void themeIoDone(void *arg)
{
	ThemeIoJob *j = (ThemeIoJob *)arg;

	if (j->abandoned) {
		free(j->text);
		free(j);
	}
}

/* 1 = finished (caller owns j), 0 = user backed out (job frees itself) */
static int themeIo(ThemeIoJob *j, const char *title)
{
	int id = dashWorkerSubmit(title, DASH_JOB_THEME | DASH_JOB_VISIBLE, themeIoRun, themeIoDone, j);

	if (id < 0) {
		free(j->text);
		free(j);
		dashToast(DASH_TOAST_WARN, "Theme operation could not be queued; try again");
		return 0;
	}

	if (dashWorkerAwait(id, title, 1))
		return 1;
	j->abandoned = 1;
	return 0;
}

void dashSettingsSaveTheme(void)
{
	ThemeIoJob *j;
	char name[DASH_THEME_NAME_MAX], body[200];
	int i;

	dashStrCopy(name, dashTheme.name, sizeof(name));
	for (i = 0; name[i]; i++) {
		char ch = name[i];
		if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_'))
			name[i] = '_';
	}
	if (name[0] == '\0')
		strcpy(name, "MyTheme");
	snprintf(body, sizeof(body), "Save the current theme as %sTHEMES/%s/theme.cfg? An existing theme with that name is replaced.",
	         dashStoreDir(), name);
	if (!dashModalConfirm("Save theme", body, "Save", 0))
		return;
	j = (ThemeIoJob *)malloc(sizeof(ThemeIoJob));
	if (j == NULL)
		return;
	memset(j, 0, sizeof(*j));
	j->op = TIO_WRITE;
	dashStrCopy(j->folder, name, sizeof(j->folder));
	j->text = dashThemeFolderText(&j->len);
	if (j->text == NULL) {
		free(j);
		return;
	}
	if (!themeIo(j, "Saving theme"))
		return;
	if (j->ret == 0)
		dashToast(DASH_TOAST_OK, "Theme saved");
	else
		dashModalMessage(DI_WARNING, "Theme not saved", "The theme folder could not be written. Check that the device is writable.", NULL);
	free(j->text);
	free(j);
}

int dashSettingsLoadTheme(void)
{
	ThemeIoJob *j = (ThemeIoJob *)malloc(sizeof(ThemeIoJob));
	DashMenuItem items[24];
	int i, r, changed = 0;
	char body[200];

	if (j == NULL)
		return 0;
	memset(j, 0, sizeof(*j));
	j->op = TIO_LIST;
	if (!themeIo(j, "Looking for themes"))
		return 0;
	if (j->n <= 0) {
		snprintf(body, sizeof(body), "Put each theme in its own folder with a theme.cfg inside %sTHEMES/. "
		                             "\"Export theme to folder\" creates one you can copy and edit.", dashStoreDir());
		dashModalMessage(DI_FOLDER, "No themes found", body, NULL);
		free(j);
		return 0;
	}
	for (i = 0; i < j->n; i++) {
		items[i].icon = DI_PALETTE;
		items[i].label = j->names[i];
		items[i].detail = NULL;
		items[i].disabled = 0;
	}
	r = dashModalMenu("Load theme", "THEMES folder", items, j->n, 0);
	if (r < 0) {
		free(j);
		return 0;
	}
	j->op = TIO_READ;
	dashStrCopy(j->folder, j->names[r], sizeof(j->folder));
	if (!themeIo(j, "Loading theme"))
		return 0;
	if (j->ret == 0) {
		dashTheme = j->t;
		dashThemeCommit();
		changed = 1;
		dashToast(DASH_TOAST_OK, "Theme loaded");
	} else
		dashModalMessage(DI_WARNING, "Theme not loaded", "theme.cfg is missing or could not be read.", j->folder);
	free(j);
	return changed;
}

