#include "filer_saves_internal.h"

/* Archive actions run on the UI thread after transfer preflight. dash_io
 * redraws during serialized async RPC waits without dispatching other I/O.
 * Reuse the paste popup, publishing measured bytes from the streaming loops.
 * Listing probes and Copy/Cut never enable this context. */
FilerSaveProgress save_progress;

void saveProgressBegin(int count)
{
	memset(&save_progress, 0, sizeof(save_progress));
	save_progress.active = 1;
	save_progress.count = count;
}

void saveProgressEnd(void)
{
	if (save_progress.classic_drawn) nonDialog(NULL);
	if (save_progress.active) DashFileOperationEnd();
	memset(&save_progress, 0, sizeof(save_progress));
}

void saveProgressStage(const char *action, const char *name)
{
	char text[384];
	if (!save_progress.active) return;
	save_progress.action = action;
	if (DashFileOperationStatus(action, name, save_progress.index, save_progress.count) || DashIsActive()) return;
	if (save_progress.classic_drawn) nonDialog(NULL);
	snprintf(text, sizeof(text), "%s %llu of %llu\n%.255s", action,
	         (unsigned long long)save_progress.index, (unsigned long long)save_progress.count, name);
	nonDialog(text); drawMsg(name);
	save_progress.classic_drawn = 1;
	save_progress.last_draw = Timer();
}

void saveProgressItem(int index, const char *name, const char *action)
{
	save_progress.index = index;
	save_progress.verifying = 0;
	snprintf(save_progress.item, sizeof(save_progress.item), "%s", name);
	saveProgressStage(action, name);
}

void saveProgressBytes(const char *path, u64 done, u64 total)
{
	DashTransferStats stats = {0};
	char name[128], text[512], speed_text[40], time_text[40];
	const char *leaf;
	u64 now, elapsed, speed;
	if (!save_progress.active) return;
	now = Timer(); elapsed = now >= save_progress.started ? now - save_progress.started : 0;
	if (done >= save_progress.file_done) {
		u64 delta = done - save_progress.file_done;
		save_progress.bytes += delta;
		if (save_progress.extracting) save_progress.extract_done += delta;
	}
	save_progress.file_done = done;
	if (save_progress.extracting) {
		done = save_progress.extract_done; total = save_progress.extract_total;
		/* File closes and save metadata must succeed before showing 100%.
		 * Empty saves remain in the named stage until metadata is restored. */
		if (done == total && !save_progress.extract_complete) return;
	}
	speed = elapsed ? (u64)done * 1000 / elapsed : 0;
	stats.current_speed = stats.average_speed = elapsed ? (speed > 0x7fffffffULL ? 0x7fffffff : (int)speed) : -1;
	stats.remaining_seconds = done == total ? 0 : speed ? (int)((total - done) / speed) : -1;
	stats.written_total = save_progress.bytes;
	stats.file_index = save_progress.index; stats.file_count = save_progress.count;
	leaf = strrchr(path, '/'); leaf = leaf ? leaf + 1 : path;
	if (save_progress.extracting)
		snprintf(name, sizeof(name), "%.127s", save_progress.extract_name);
	else if (strcmp(leaf, save_progress.item))
		snprintf(name, sizeof(name), "%.64s / %.59s", save_progress.item, leaf);
	else snprintf(name, sizeof(name), "%s", leaf);
	if (DashFileTransferProgress(save_progress.action, name, total - done, total, &stats) || DashIsActive()) return;
	if (done != total && now - save_progress.last_draw < 30) return;
	if (save_progress.classic_drawn) nonDialog(NULL);
	if (stats.average_speed < 0) snprintf(speed_text, sizeof(speed_text), "Unknown");
	else snprintf(speed_text, sizeof(speed_text), "%d B/s", stats.average_speed);
	if (stats.remaining_seconds < 0) snprintf(time_text, sizeof(time_text), "Unknown");
	else snprintf(time_text, sizeof(time_text), "%d sec", stats.remaining_seconds);
	snprintf(text, sizeof(text), "%s %llu of %llu\n%s\n%llu / %llu bytes (%d%%)\nAverage speed: %s\nRemaining time: %s",
	         save_progress.action, (unsigned long long)save_progress.index, (unsigned long long)save_progress.count, name,
	         (unsigned long long)done, (unsigned long long)total, total ? (int)((u64)done * 100 / total) : 100,
	         speed_text, time_text);
	nonDialog(text); drawMsg(name);
	save_progress.classic_drawn = 1; save_progress.last_draw = now;
}

void saveProgressFile(const char *path, size_t size)
{
	if (!save_progress.active) return;
	if (!save_progress.extracting) save_progress.started = Timer();
	save_progress.file_done = 0;
	if (size) saveProgressBytes(path, 0, size);
}

/* Extraction publishes one byte total and one stable label for the save.
 * Keep the batch ordinal; individual output files never reset its bar/ETA. */
void saveProgressExtractBegin(const SaveArchive *save, const char *name)
{
	if (!save_progress.active) return;
	save_progress.extracting = 1; save_progress.extract_complete = 0;
	save_progress.extract_done = save_progress.extract_total = save_progress.file_done = 0;
	save_progress.started = Timer();
	snprintf(save_progress.extract_name, sizeof(save_progress.extract_name), "%s", name);
	for (unsigned i = 0; i < save->count; i++) save_progress.extract_total += save->files[i].size;
	saveProgressBytes(name, 0, 0);
}

void saveProgressExtractEnd(int success)
{
	if (!save_progress.extracting) return;
	if (success) {
		save_progress.extract_complete = 1;
		/* Re-publish the last per-file count without counting its bytes twice. */
		saveProgressBytes(save_progress.extract_name, save_progress.file_done, 0);
	}
	save_progress.extracting = save_progress.extract_complete = 0;
	save_progress.extract_done = save_progress.extract_total = 0;
	save_progress.extract_name[0] = '\0';
}

