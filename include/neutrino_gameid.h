#ifndef NEUTRINO_GAMEID_H
#define NEUTRINO_GAMEID_H

#include <stddef.h>

#define NEUTRINO_GAME_ID_SIZE 12

/* Read from ISO9660 SYSTEM.CNF without switching or loading drivers. */
int prepareNeutrinoGameID(const char *iso_path, char *gameID, size_t gameID_len);

#ifdef MMCE
/* R3Z 4.80 VMC selection: skip MX4SIO, protect the resolved mcN: ELF slot.
 * mmceN: ISO/ELF files do not exclude their adapter. Recheck MMCE without
 * replacing the prepared storage stack. */
void setNeutrinoMmceGameID(const char *gameID, const char *iso_path, const char *elf_path);
#endif

#endif
