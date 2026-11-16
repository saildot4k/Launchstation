#include "dash_vu1.h"
#include "dash_profile.h"
#include <math.h>
#include <string.h>

typedef union { float f[4]; uint32_t u[4]; } VuQuadword;
size_t dashVu1BuildPacket(uint32_t *words, size_t capacity, const DashVu1Screen *s,
	const DashVu1Vertex *vertices, unsigned quads, unsigned mark)
{
	VuQuadword input[DASH_VU1_INPUT_QWORDS];
	size_t position = 0, qw = DASH_VU1_UNIFORMS + quads * 8, consumed = 0;
	if (!words || !s || !vertices || !quads || quads > DASH_VU1_QUADS || !mark || mark > 65535 ||
	    !isfinite(s->scale_x) || !isfinite(s->scale_y) || !isfinite(s->cx) || !isfinite(s->cy) ||
	    s->scale_x <= 0 || s->scale_x > 4 || s->scale_y <= 0 || s->scale_y > 2 ||
	    fabsf(s->cx) > 8192 || fabsf(s->cy) > 8192 || s->offset_x > 65535 || s->offset_y > 65535 || s->context > 1 ||
	    capacity < 4 + ((qw + 255) / 256) * 4 + qw * 4 + 4) return 0;
	for (unsigned i = 0; i < quads * 4; i++) {
		if (!isfinite(vertices[i].direction[0]) || !isfinite(vertices[i].direction[1]) ||
		    !isfinite(vertices[i].direction[2]) || fabsf(vertices[i].direction[0]) > 2 ||
		    fabsf(vertices[i].direction[1]) > 2 || vertices[i].direction[2] < 0 || vertices[i].direction[2] > 4096) return 0;
		for (unsigned j = 0; j < 4; j++) if (vertices[i].color[j] > (j == 3 ? 128u : 255u)) return 0;
	}
	memset(input, 0, DASH_VU1_UNIFORMS * sizeof(*input));
	input[0].f[0] = s->scale_x; input[0].f[1] = s->scale_y; input[0].f[2] = s->cx; input[0].f[3] = s->cy;
	input[1].u[0] = quads; input[1].u[1] = s->offset_x; input[1].u[2] = s->offset_y;
	/* Four vertices per strip; EOP only on the final FINISH tag. A single
	 * XGKICK must consume every strip, not stop after the first one. */
	input[2].u[0] = 4;
	input[2].u[1] = (2u << 28) | ((4u | 8u | 64u | (s->context << 9)) << 15) | (1u << 14);
	input[2].u[2] = 0x51; /* RGBAQ, XYZ2 */
	input[3].u[0] = 1u | (1u << 15); input[3].u[1] = 1u << 28; input[3].u[2] = 0x0e;
	input[4].u[2] = 0x61; /* A+D: FINISH */
	input[5].f[0] = -(float)s->offset_x / 16; input[5].f[1] = -(float)s->offset_y / 16;
	input[6].f[0] = (65535.0f - s->offset_x) / 16; input[6].f[1] = (65535.0f - s->offset_y) / 16;
	memcpy(input + DASH_VU1_UNIFORMS, vertices, quads * 4 * sizeof(*vertices));
	words[position++] = 0x01000101; /* STCYCL: one write per cycle */
	words[position++] = 0x05000000; /* STMOD: normal unpack */
	words[position++] = 0x20000000; words[position++] = 0; /* STMASK: unmasked */
	while (consumed < qw) {
		unsigned n = qw - consumed > 256 ? 256 : qw - consumed;
		while ((position & 3) != 3) words[position++] = 0;
		words[position++] = 0x6c000000 | ((n & 255) << 16) | consumed; /* UNPACK V4_32 */
		memcpy(words + position, input + consumed, n * 16); position += n * 4; consumed += n;
	}
	words[position++] = 0x14000000; /* MSCAL 0 */
	words[position++] = 0x13000000; /* FLUSHA: VU1 and GIF paths, not just DMA */
	words[position++] = 0x07000000 | mark; /* MARK observes FLUSHA completion */
	words[position++] = 0;
	return position;
}

#if defined(_EE) && DASH_VU1
#include <kernel.h>
#include <dmaKit.h>
#include <ee_regs.h>
/* Program and input/output occupy separate local-memory regions: input
 * [0,263), output [512,802). Both fit the 1024-qword VU1 data memory. */
extern const unsigned char dashVu1TunnelStart[], dashVu1TunnelEnd[];
static uint32_t packet[DASH_VU1_PACKET_WORDS] __attribute__((aligned(64)));
static DashVu1Vertex queued[DASH_VU1_QUADS * 4] __attribute__((aligned(16)));
static DashVu1Screen screen;
static int loaded_generation = -1, disabled, active;
static unsigned queued_quads, token;
int dashVu1Available(void) { return !disabled; }
static uint32_t countNow(void) { uint32_t value; __asm__ volatile("mfc0 %0, $9" : "=r"(value)); return value; }
static int fail(void)
{
	/* Stop DMA before reusing packet storage. Only the experimental render
	 * channels are reset; the existing IOP, audio and storage are untouched. */
	*R_EE_D1_CHCR = 0;
	__asm__ volatile("sync.l" : : : "memory");
	ResetEE(INIT_VU1 | INIT_VIF1 | INIT_GIF);
	disabled = 1; active = 0; queued_quads = 0;
	return 0;
}
static int send(size_t words, unsigned expected, int finish)
{
	uint32_t start = countNow();
	dmaKit_send(DMA_CHANNEL_VIF1, packet, words / 4);
	/* A fixed Count budget bounds a broken prototype. MARK follows FLUSHA;
	 * DMA completion alone does not establish that XGKICK consumed its data. */
	while ((*R_EE_D1_CHCR & 0x100) || ((*R_EE_VIF1_MARK & 65535) != expected) ||
	    (finish && !(*((volatile uint64_t *)0x12001000) & 2))) {
		if ((uint32_t)(countNow() - start) > 30000000u) return fail();
	}
	return 1;
}
static unsigned nextToken(void) { token = (*R_EE_VIF1_MARK & 65535) % 65535 + 1; return token; }
int dashVu1Begin(const DashVu1Screen *s, int generation)
{
	if (disabled || active || !s) return 0;
	if (loaded_generation != generation) {
		size_t bytes = dashVu1TunnelEnd - dashVu1TunnelStart;
		if (!bytes || (bytes & 15) || bytes > 2048) return fail();
		if (dmaKit_chan_init(DMA_CHANNEL_VIF1) < 0) return fail();
		ResetEE(INIT_VU1 | INIT_VIF1);
		packet[0] = packet[1] = packet[2] = 0;
		packet[3] = 0x4a000000 | (((bytes / 8) & 255) << 16); /* MPG */
		memcpy(packet + 4, dashVu1TunnelStart, bytes);
		unsigned expected = nextToken();
		packet[4 + bytes/4] = 0x10000000; /* FLUSHE */
		packet[5 + bytes/4] = 0x07000000 | expected;
		packet[6 + bytes/4] = packet[7 + bytes/4] = 0;
		if (!send(8 + bytes/4, expected, 0)) return 0;
		loaded_generation = generation;
	}
	screen = *s; queued_quads = 0; active = 1;
	return 1;
}
static int flush(void)
{
	if (!active) return 0;
	if (!queued_quads) return 1;
	uint32_t started = dashProfileNow();
	unsigned expected = nextToken();
	size_t words = dashVu1BuildPacket(packet, DASH_VU1_PACKET_WORDS, &screen, queued, queued_quads, expected);
	if (!words) return fail();
	*((volatile uint64_t *)0x12001000) = 2; /* acknowledge old GS FINISH */
	int result = send(words, expected, 1);
	dashProfileEnd(DASH_PROF_VU1, started);
	queued_quads = 0;
	return result;
}
int dashVu1Append(const DashVu1Vertex vertices[4])
{
	if (!active || !vertices) return 0;
	if (queued_quads == DASH_VU1_QUADS && !flush()) return 0;
	memcpy(queued + queued_quads * 4, vertices, sizeof(*vertices) * 4); queued_quads++;
	return 1;
}
int dashVu1End(void) { int result = flush(); active = 0; return result; }
#else
int dashVu1Available(void) { return 0; }
int dashVu1Begin(const DashVu1Screen *screen, int generation) { (void)screen; (void)generation; return 0; }
int dashVu1Append(const DashVu1Vertex vertices[4]) { (void)vertices; return 0; }
int dashVu1End(void) { return 0; }
#endif
