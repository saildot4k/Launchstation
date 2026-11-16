#include "dash_vu_math.h"
#include "dash_profile.h"
#include <stdint.h>
#if defined(_EE) && DASH_VU0
#include <kernel.h>
#endif
void dashVuTowerProjectCpu(const DashVuCamera *c, const DashVuTower *tower, size_t count, DashVuProjection *out)
{
	float floor_scale = c->f / (c->cam_h - c->floor_h);
	for (size_t i = 0; i < count; i++) {
		float top_scale = c->f / (c->cam_h - tower[i].h);
		for (unsigned j = 0; j < 4; j++) {
			float x = tower[i].x + (j & 1 ? c->half_width : -c->half_width);
			float y = tower[i].y + (j & 2 ? c->half_width : -c->half_width);
			float rx = x * c->ca - y * c->sa, ry = x * c->sa + y * c->ca;
			out[i].tx[j] = c->cx + rx * top_scale * 1.12f;
			out[i].ty[j] = c->cy + ry * top_scale;
			out[i].bx[j] = c->cx + rx * floor_scale * 1.12f;
			out[i].by[j] = c->cy + ry * floor_scale;
		}
	}
}
void dashVuTowerProject(const DashVuCamera *c, const DashVuTower *tower, size_t count, DashVuProjection *out)
{
#if defined(_EE) && DASH_VU0
	static const float dx[4] __attribute__((aligned(16))) = {-1,1,-1,1};
	static const float dy[4] __attribute__((aligned(16))) = {-1,-1,1,1};
	static const float aspect[4] __attribute__((aligned(16))) = {1.12f,0,0,0};
	if (((uintptr_t)c | (uintptr_t)tower | (uintptr_t)out) & 15) {
		dashVuTowerProjectCpu(c, tower, count, out); return;
	}
	/* No callbacks, yields, DMA or library math inside these short sections.
	 * Releasing interrupts after each tower bounds preemption latency and
	 * prevents a worker/library from replacing live COP2 registers. */
	for (size_t i = 0; i < count; i++) {
		int interrupted = DIntr();
		__asm__ volatile(
			"lqc2 $vf1, 0(%0)\n lqc2 $vf2, 16(%0)\n"
			"lqc2 $vf3, 0(%3)\n lqc2 $vf4, 0(%4)\n lqc2 $vf5, 0(%5)\n"
			"vmulz.xyzw $vf3, $vf3, $vf2z\n vmulz.xyzw $vf4, $vf4, $vf2z\n"
			"vsubw.x $vf6, $vf2, $vf2w\n vdiv $Q, $vf2y, $vf6x\n vwaitq\n"
			"vaddq.x $vf7, $vf0, $Q\n lqc2 $vf8, 0(%1)\n"
			"vaddx.xyzw $vf9, $vf3, $vf8x\n vaddy.xyzw $vf10, $vf4, $vf8y\n"
			"vsubz.x $vf6, $vf2, $vf8z\n vdiv $Q, $vf2y, $vf6x\n"
			"vmulx.xyzw $vf11, $vf9, $vf1x\n vmuly.xyzw $vf12, $vf10, $vf1y\n"
			"vsub.xyzw $vf11, $vf11, $vf12\n"
			"vmuly.xyzw $vf12, $vf9, $vf1y\n vmulx.xyzw $vf13, $vf10, $vf1x\n"
			"vadd.xyzw $vf12, $vf12, $vf13\n"
			"vmulx.xyzw $vf13, $vf11, $vf7x\n vmulx.xyzw $vf13, $vf13, $vf5x\n"
			"vaddz.xyzw $vf13, $vf13, $vf1z\n sqc2 $vf13, 32(%2)\n"
			"vmulx.xyzw $vf13, $vf12, $vf7x\n vaddw.xyzw $vf13, $vf13, $vf1w\n sqc2 $vf13, 48(%2)\n"
			"vwaitq\n vmulq.xyzw $vf11, $vf11, $Q\n vmulx.xyzw $vf11, $vf11, $vf5x\n"
			"vaddz.xyzw $vf11, $vf11, $vf1z\n sqc2 $vf11, 0(%2)\n"
			"vmulq.xyzw $vf12, $vf12, $Q\n vaddw.xyzw $vf12, $vf12, $vf1w\n sqc2 $vf12, 16(%2)\n"
			: : "r"(c), "r"(&tower[i]), "r"(&out[i]), "r"(dx), "r"(dy), "r"(aspect) : "memory");
		if (interrupted) EIntr();
	}
#else
	dashVuTowerProjectCpu(c, tower, count, out);
#endif
}
