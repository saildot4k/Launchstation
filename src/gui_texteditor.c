#include "gui_texteditor.h"

static int isDirectoryEntry(const FILEINFO *file)
{
	return (file->stats.AttrFile & sceMcFileAttrSubdir) != 0;
}

static int isParentEntry(const FILEINFO *file)
{
	return !strcmp(file->name, "..");
}

int canOpenInTextEditor(const char *path, const FILEINFO *file)
{
	if (isDirectoryEntry(file) || isParentEntry(file))
		return FALSE;

	/* Use the same file types as opening a document in the Text Editor. */
	if (!strcmp(path, setting->Misc))
		return FALSE;

	return IsTextEditorFileType(file->name);
}
