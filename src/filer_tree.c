#include "filer_tree.h"
#include "filer_shared.h"
#include "gui_hdd0_format.h"

#define TREE_DEPTH_LIMIT 16
#define TREE_METADATA_LIMIT (2 * 1024 * 1024)
typedef struct { char name[MAX_NAME]; unsigned attr; } TreeChild;
typedef struct {
	FILEINFO *scratch;
	size_t retained;
	FilerTreeVisit visit;
	void *context;
} TreeWalk;

static int walk(TreeWalk *tree, const char *parent, const FILEINFO *file, int depth)
{
	char path[MAX_PATH];
	TreeChild *children = NULL;
	FILEINFO child;
	int count = 0, result = 0;
	size_t bytes = 0;
	if (depth >= TREE_DEPTH_LIMIT) return -ELOOP;
	if (file->stats.AttrFile & sceMcFileAttrSubdir) {
		if (snprintf(path, sizeof(path), "%s%s/", parent, file->name) >= (int)sizeof(path)) return -ENAMETOOLONG;
		if (!tree->scratch) {
			tree->scratch = malloc(MAX_ENTRY * sizeof(*tree->scratch));
			if (!tree->scratch) return -ENOMEM;
			tree->retained = MAX_ENTRY * sizeof(*tree->scratch);
			if (tree->retained > TREE_METADATA_LIMIT) return -ENOMEM;
		}
		count = getDir(path, tree->scratch);
		if (count < 0) return count;
		/* A full browser listing may be truncated; MC also removes . and ..
		 * after its capped RPC, so reserve those two slots conservatively. */
		if (count >= MAX_ENTRY - 4) return -EOVERFLOW;
		bytes = count * sizeof(*children);
		if (bytes > TREE_METADATA_LIMIT - tree->retained) return -ENOMEM;
		if (count && !(children = malloc(bytes))) return -ENOMEM;
		tree->retained += bytes;
		for (int i = 0; i < count; i++) {
			const FILEINFO *entry = &tree->scratch[i];
			if (!memchr(entry->name, 0, sizeof(entry->name)) || !entry->name[0] ||
			    strchr(entry->name, '/') || strchr(entry->name, '\\')) { result = -EINVAL; goto done; }
			strcpy(children[i].name, entry->name); children[i].attr = entry->stats.AttrFile;
		}
		for (int i = 0; i < count; i++) {
			if (!strcmp(children[i].name, ".") || !strcmp(children[i].name, "..")) continue;
			memset(&child, 0, sizeof(child));
			strcpy(child.name, children[i].name); child.stats.AttrFile = children[i].attr;
			result = walk(tree, path, &child, depth + 1);
			if (result < 0) goto done;
		}
	}
	result = tree->visit(parent, file, tree->context);
done:
	free(children); tree->retained -= bytes;
	return result;
}

int filerWalkTree(const char *path, const FILEINFO *file, FilerTreeVisit visit, void *context)
{
	TreeWalk tree = {0};
	int result;
	if (!path || !file || !visit) return -EINVAL;
	tree.visit = visit; tree.context = context;
	result = walk(&tree, path, file, 0);
	free(tree.scratch);
	return result;
}

static int measureTreeEntry(const char *path, const FILEINFO *file, void *context)
{
	iox_stat_t stat;
	u64 size;
	char dir[MAX_PATH], party[MAX_NAME];
	int ret;

	if (file->stats.AttrFile & sceMcFileAttrSubdir) return 0;
	if (!ensurePathDeviceStackReady(path)) return -1;
	if (snprintf(dir, sizeof(dir), "%s%s", path, file->name) >= (int)sizeof(dir)) return -ENAMETOOLONG;
	if (!strncmp(path, "hdd", 3)) {
		if (getHddParty(path, file, party, dir) < 0) return -1;
		ret = mountParty(party);
		if (ret < 0) return ret;
		dir[3] = ret + '0';
#ifdef DVRP
	} else if (!strncmp(path, "dvr_hdd", 7)) {
		if (getHddDVRPParty(path, file, party, dir) < 0) return -1;
		ret = mountDVRPParty(party);
		if (ret < 0) return ret;
		dir[7] = ret + '0';
#endif
	}
#if defined(ETH) || defined(UDPFS)
	if (!strncmp(dir, "host:/", 6)) makeHostPath(dir, dir);
#endif
	ret = genGetStat(dir, &stat);
	if (ret < 0) return ret;
	size = ((u64)stat.hisize << 32) | (u64)stat.size;
	if (size > ~(u64)0 - *(u64 *)context) return -EOVERFLOW;
	*(u64 *)context += size;
	return 0;
}

int getFileSize(const char *path, const FILEINFO *file, u64 *size)
{
	u64 measured = 0;
	int result;

	if (!size || !ensurePathDeviceStackReady(path)) return -1;
	result = filerWalkTree(path, file, measureTreeEntry, &measured);
	if (result >= 0) *size = measured;
	return result;
}
