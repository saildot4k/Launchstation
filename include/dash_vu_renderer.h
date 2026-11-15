#ifndef DASH_VU_RENDERER_H
#define DASH_VU_RENDERER_H
#include <stdint.h>
/* Begin returns 1 when active, 0 for normal CPU fallback, or -1 after
 * recovering a fault. The caller must requeue its clear after recovery. */
int dashGfxVu1Begin(float cx, float cy);
int dashGfxVu1Quad(float ca0, float sa0, float ca1, float sa1, float near_radius, float far_radius,
                   uint32_t near_rgba, uint32_t far_rgba);
int dashGfxVu1End(void);
#endif
