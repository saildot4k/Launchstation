#ifndef DASH_VU1_H
#define DASH_VU1_H
#include <stddef.h>
#include <stdint.h>
#define DASH_VU1_QUADS 32
#define DASH_VU1_UNIFORMS 7
#define DASH_VU1_INPUT_QWORDS (DASH_VU1_UNIFORMS + DASH_VU1_QUADS * 8)
#define DASH_VU1_PACKET_WORDS 1088
/* VU1 input [direction.x, direction.y, radius, unused], then packed RGBAQ
 * components in four words. Output is untextured, opaque triangle strips. */
typedef struct { float direction[4]; uint32_t color[4]; } DashVu1Vertex;
typedef struct { float scale_x, scale_y, cx, cy; uint32_t offset_x, offset_y, context; } DashVu1Screen;
/* Pure packet builder, also exercised on host. Returns 0 on invalid input or
 * insufficient capacity, otherwise the aligned DMA packet word count. */
size_t dashVu1BuildPacket(uint32_t *words, size_t capacity, const DashVu1Screen *screen,
 const DashVu1Vertex *vertices, unsigned quads, unsigned mark);
/* Synchronous renderer-only prototype: no operation returns with DMA/VU/GIF
 * reading its buffers. Failure disables VU1 until the app is restarted. */
int dashVu1Available(void);
int dashVu1Begin(const DashVu1Screen *screen, int generation);
int dashVu1Append(const DashVu1Vertex vertices[4]);
int dashVu1End(void);
#endif
