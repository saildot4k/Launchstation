#include "dash_profile.h"
#if DASH_PROFILE
#include <stdio.h>
#include <string.h>
#define PROFILE_SAMPLES 128
static struct {
	uint64_t total, calls;
	uint32_t maximum, samples[PROFILE_SAMPLES];
} samples[DASH_PROF_COUNT];
static unsigned frames;
static int reporting;
static const char *const names[] = {"frame-build", "background", "tower-project", "tunnel",
	"present-wait", "icon-init", "glow-init", "vu1-submit-wait"};
uint32_t dashProfileNow(void)
{
#ifdef _EE
	uint32_t value;
	__asm__ volatile("mfc0 %0, $9" : "=r"(value));
	return value;
#else
	extern uint32_t dashProfileHostCounter(void);
	return dashProfileHostCounter();
#endif
}
void dashProfileEnd(enum DashProfileSlot slot, uint32_t start)
{
	uint32_t ticks = dashProfileNow() - start;
	if (reporting || (unsigned)slot >= DASH_PROF_COUNT) return;
	samples[slot].samples[samples[slot].calls % PROFILE_SAMPLES] = ticks;
	samples[slot].calls++; samples[slot].total += ticks;
	if (ticks > samples[slot].maximum) samples[slot].maximum = ticks;
}
void dashProfileReset(void) { memset(samples, 0, sizeof(samples)); frames = 0; }
void dashProfileReport(void)
{
	uint32_t sorted[PROFILE_SAMPLES];
	if (reporting) return;
	reporting = 1;
	for (int slot = 0; slot < DASH_PROF_COUNT; slot++) {
		unsigned n = samples[slot].calls < PROFILE_SAMPLES ? samples[slot].calls : PROFILE_SAMPLES;
		if (!n) continue;
		memcpy(sorted, samples[slot].samples, n * sizeof(*sorted));
		for (unsigned i = 1; i < n; i++) {
			uint32_t value = sorted[i]; unsigned j = i;
			while (j && sorted[j-1] > value) { sorted[j] = sorted[j-1]; j--; }
			sorted[j] = value;
		}
		printf("[dash-profile] vu0=%d vu1=%d reference=%d slot=%s calls=%llu mean=%llu max=%u p50=%u p95=%u samples=%u unit=count-ticks\n",
			DASH_VU0, DASH_VU1, DASH_VU1_REFERENCE, names[slot], (unsigned long long)samples[slot].calls,
			(unsigned long long)(samples[slot].total / samples[slot].calls), (unsigned)samples[slot].maximum,
			(unsigned)sorted[(n-1)/2], (unsigned)sorted[(95*n+99)/100-1], n);
	}
	reporting = 0;
}
/* Caller checks foreground RPC ownership; reporting is outside measured work. */
void dashProfileFrameComplete(void) { if (!reporting && ++frames % 600 == 0) dashProfileReport(); }
#endif
