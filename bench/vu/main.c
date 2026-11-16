/* Standalone PS2 probe: real COP2/VIF1/VU1/GIF execution and comparisons.
 * stdout is suitable for ps2link/serial capture. No filesystem or IOP reset. */
#include <kernel.h>
#include <gsKit.h>
#include <dmaKit.h>
#include <stdio.h>
#include <math.h>
#include "dash_profile.h"
#include "dash_vu_math.h"
#include "dash_vu1.h"
#define TOWERS 165
static DashVuCamera camera __attribute__((aligned(16)));
static DashVuTower towers[TOWERS] __attribute__((aligned(16)));
static DashVuProjection reference[TOWERS] __attribute__((aligned(16)));
static DashVuProjection actual[TOWERS] __attribute__((aligned(16)));
static int failures;
static volatile float checksum;
static void check(int ok, const char *name)
{
	if (!ok) { if (failures < 10) printf("[vu-probe] FAIL %s\n", name); failures++; }
}
static void towerTest(void)
{
	float maximum = 0;
	for (int frame = 0; frame < 120; frame++) {
		float a = frame * 0.1f;
		camera = (DashVuCamera){cosf(a), sinf(a), 320, 224, 150+15*sinf(a), 300, 3.7f, -40};
		for (int i = 0; i < TOWERS; i++) towers[i] = (DashVuTower){(i%15-7)*10, (i/15-5)*10, 8+i%89, 1};
		dashVuTowerProjectCpu(&camera, towers, TOWERS, reference);
		dashVuTowerProject(&camera, towers, TOWERS, actual);
		const float *expected = (const float *)reference, *got = (const float *)actual;
		for (unsigned i = 0; i < TOWERS * 16; i++) {
			float error = fabsf(expected[i]-got[i]);
			check(isfinite(got[i]) && error < 0.02f, "VU0 scalar agreement");
			if (error > maximum) maximum = error;
		}
	}
	printf("[vu-probe] vu0 maximum_virtual_pixel_error=%f\n", (double)maximum);
	for (int accelerated = 0; accelerated <= 1; accelerated++) {
		uint32_t start = dashProfileNow();
		for (unsigned i = 0; i < 256; i++) {
			if (accelerated) dashVuTowerProject(&camera, towers, TOWERS, actual);
			else dashVuTowerProjectCpu(&camera, towers, TOWERS, actual);
			checksum += actual[i%TOWERS].tx[i%4];
		}
		uint32_t elapsed = dashProfileNow()-start;
		printf("[vu-probe] kernel=%s towers=%d batches=256 elapsed_count_ticks=%u\n", accelerated ? "vu0" : "cpu", TOWERS, (unsigned)elapsed);
	}
}
static void vu1Test(GSGLOBAL *gs)
{
	DashVu1Screen s = {1.18f, 1, 320, 224, gs->OffsetX, gs->OffsetY, gs->PrimContext};
	DashVu1Vertex vertices[4] = {
		{{-1,-1,25,0},{255,0,0,128}},{{1,-1,25,0},{0,255,0,128}},
		{{-1,1,25,0},{0,0,255,128}},{{1,1,25,0},{255,255,255,128}}
	};
	const unsigned counts[] = {1,32,65};
	for (unsigned test = 0; test < sizeof(counts)/sizeof(*counts); test++) {
		check(dashVu1Begin(&s, 1), "VU1 upload/begin");
		for (unsigned i = 0; i < counts[test]; i++) check(dashVu1Append(vertices), "VU1 append/flush");
		if (!dashVu1End()) { check(0,"VU1 completion/fence"); return; }
		unsigned last = counts[test] % DASH_VU1_QUADS;
		if (!last) last = DASH_VU1_QUADS;
		volatile uint32_t *output = (volatile uint32_t *)(0x1100c000 + 512*16);
		for (unsigned quad = 0; quad < last; quad++) {
			unsigned pos = quad*36;
			check(output[pos]==4 && output[pos+2]==0x51, "VU1 GIF strip header");
			for (unsigned vertex = 0; vertex < 4; vertex++) {
				pos = quad*36+4+vertex*8;
				for (unsigned lane = 0; lane < 4; lane++) check(output[pos+lane]==vertices[vertex].color[lane], "VU1 color");
				for (unsigned lane = 0; lane < 2; lane++) {
	    float scale = lane ? s.scale_y : s.scale_x, center = lane ? s.cy : s.cx;
	    int expected = (int)((center+vertices[vertex].direction[lane]*25*scale)*16) + (lane ? s.offset_y : s.offset_x);
	    int difference = (int)output[pos+4+lane]-expected;
	    check(difference >= -1 && difference <= 1, "VU1 GS coordinates");
				}
			}
		}
		unsigned end = last*36;
		check(output[end]==32769 && output[end+4+2]==0x61, "VU1 final EOP/FINISH");
		printf("[vu-probe] vu1 quads=%u completed\n", counts[test]);
	}
}
int main(void)
{
	towerTest();
	GSGLOBAL *gs = gsKit_init_global();
	if (!gs) { printf("[vu-probe] FAIL GS allocation\n"); SleepThread(); return 1; }
	gs->DoubleBuffering = GS_SETTING_ON; gs->ZBuffering = GS_SETTING_OFF;
	dmaKit_init(D_CTRL_RELE_OFF,D_CTRL_MFD_OFF,D_CTRL_STS_UNSPEC,D_CTRL_STD_OFF,D_CTRL_RCYC_8,1<<DMA_CHANNEL_GIF);
	dmaKit_chan_init(DMA_CHANNEL_GIF);
	gsKit_init_screen(gs); gsKit_mode_switch(gs,GS_ONESHOT);
	gsKit_clear(gs,GS_SETREG_RGBAQ(0,0,0,0,0));
	gsKit_queue_exec(gs); dmaKit_wait_fast(); gsKit_finish();
	vu1Test(gs);
	gsKit_sync_flip(gs);
	dashProfileReport();
	printf("[vu-probe] %s failures=%d\n", failures ? "FAIL" : "PASS", failures);
	SleepThread();
	return failures != 0;
}
