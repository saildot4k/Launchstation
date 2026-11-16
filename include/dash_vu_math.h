#ifndef DASH_VU_MATH_H
#define DASH_VU_MATH_H
#include <stddef.h>
/* Aligned, caller-owned geometry. All four vector lanes hold independent
 * corners. Keep the scalar reference for comparisons on host and console. */
typedef struct { float x, y, h, lum; } DashVuTower;
typedef struct { float ca, sa, cx, cy, cam_h, f, half_width, floor_h; } DashVuCamera;
typedef struct { float tx[4], ty[4], bx[4], by[4]; } DashVuProjection;
void dashVuTowerProjectCpu(const DashVuCamera *camera, const DashVuTower *tower, size_t count, DashVuProjection *out);
void dashVuTowerProject(const DashVuCamera *camera, const DashVuTower *tower, size_t count, DashVuProjection *out);
#endif
