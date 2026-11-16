#ifndef DASH_PROFILE_H
#define DASH_PROFILE_H
#include <stdint.h>
#ifndef DASH_PROFILE
#define DASH_PROFILE 0
#endif
#ifndef DASH_VU0
#define DASH_VU0 0
#endif
#ifndef DASH_VU1
#define DASH_VU1 0
#endif
#ifndef DASH_VU1_REFERENCE
#define DASH_VU1_REFERENCE 0
#endif
/* Renderer-owned elapsed Count ticks, not CPU utilization. No heap or I/O in
 * recording. Only opt-in developer builds retain samples and print reports. */
enum DashProfileSlot {
	DASH_PROF_FRAME, DASH_PROF_BACKGROUND, DASH_PROF_TOWERS,
	DASH_PROF_TUNNEL, DASH_PROF_PRESENT_WAIT, DASH_PROF_ICONS,
	DASH_PROF_GLOWS, DASH_PROF_VU1, DASH_PROF_COUNT
};
#if DASH_PROFILE
uint32_t dashProfileNow(void);
void dashProfileEnd(enum DashProfileSlot slot, uint32_t start);
void dashProfileReport(void);
void dashProfileFrameComplete(void);
void dashProfileReset(void);
#else
static inline uint32_t dashProfileNow(void) { return 0; }
static inline void dashProfileEnd(enum DashProfileSlot slot, uint32_t start) { (void)slot; (void)start; }
static inline void dashProfileReport(void) {}
static inline void dashProfileFrameComplete(void) {}
static inline void dashProfileReset(void) {}
#endif
#endif
