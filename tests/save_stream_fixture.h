/* Included only by the host adapter after the production stream module. */
static ArchiveStream fixture_stream;
static int fixture_stream_loaded;
static uint8_t *fixture_bytes;
static size_t fixture_length;

static int fixtureRead(void *context, unsigned entry, size_t offset, void *data, size_t length)
{
 return archiveStreamRead(context, entry, offset, data, length);
}
static int fixtureWrite(void *context, size_t offset, const void *data, size_t length)
{
 if (offset > fixture_length || length > fixture_length - offset) return 0;
 memcpy(fixture_bytes + offset, data, length);
 return archiveStreamWrite(context, offset, data, length);
}
static void clearFixture(void)
{
 if (fixture_stream_loaded) archiveStreamFree(&fixture_stream);
 fixture_stream_loaded = 1;
 memset(&fixture_stream, 0, sizeof(fixture_stream));
 fixture_stream.input = fixture_stream.output = fixture_stream.entry = -1;
}
static int captureFixture(int format, const char *destination, uint8_t **data, size_t *length)
{
 SaveArchiveStreamIo io = {fixtureRead, NULL, &fixture_stream, NULL, NULL, 0, NULL};
 *data = NULL; *length = 0;
 if (!saveArchiveStream(&fixture_stream.save, format, &io, &fixture_stream.length) ||
     !archiveStreamBuffers(&fixture_stream, destination)) return -1;
 fixture_length = fixture_stream.length;
 fixture_bytes = malloc(fixture_length);
 if (!fixture_bytes) return -1;
 io.write = fixtureWrite; io.buffer = fixture_stream.buffer; io.buffer2 = fixture_stream.buffer2;
 io.buffer_size = fixture_stream.buffer_size;
 saveHashInit(&fixture_stream.hash);
 int result = saveArchiveStream(&fixture_stream.save, format, &io, length);
 if (!archiveStreamCloseInput(&fixture_stream)) result = 0;
 if (!result) { free(fixture_bytes); return -1; }
 saveHashFinish(&fixture_stream.hash, archive_stream_digest);
 archive_stream_valid = 1; archive_stream_format = format; archive_stream_length = *length;
 *data = fixture_bytes;
 return 1;
}
static int buildArchiveFixture(const char *source, const FILEINFO *file, int kind, int format,
                              uint8_t **data, size_t *length, char *name, int name_size, char *message, int size)
{
 (void)message; (void)size; clearFixture(); *data = NULL; *length = 0;
 if (!archiveStreamLoad(&fixture_stream, source, file, kind) ||
     !saveArchiveFilename(&fixture_stream.save, format, name, name_size)) return -1;
 return captureFixture(format, source, data, length);
}
static int prepareArchiveFixture(const char *destination, int format, uint8_t **data, size_t *length,
                                char *name, int name_size, char *message, int size)
{
 clearFixture(); *data = NULL; *length = 0;
 if (!archiveStreamPrepare(destination, format, &fixture_stream, name, name_size, message, size)) return -1;
 return captureFixture(format, destination, data, length);
}
static int publishArchiveFixture(const uint8_t *data, size_t length, int format, const char *destination, char *message, int size)
{
 (void)data; (void)length;
 return archiveStreamPublish(&fixture_stream, format, destination, message, size);
}
