/*
# _____     ___ ____     ___ ____
#  ____|   |    ____|   |        | |____|
# |     ___|   |____ ___|    ____| |    \    PS2DEV Open Source Project.
#-----------------------------------------------------------------------
# Copyright (c) 2009 jimmikaelkael
# Licenced under Academic Free License version 2.0
# Review ps2sdk README & LICENSE files for further details.
*/

#include <mcman.h>
#include "mcman-internal.h"
#include "vmp_sign.h"

#if defined(BUILDING_VMCMAN)
typedef struct vmc_cardinfo_
{
	int mounted;
	int opened;
	int has_ecc;
	int data_offset;
	int dirty;
	int fd;
	s16 pagesize;
	u16 blocksize;
	int cardsize;
	u8 flags;
} vmc_cardinfo_t;

static vmc_cardinfo_t mcman_vmc_cardinfo[MCMAN_MAXSLOT];

static void mcman_iomanx_backing_clear_slot(int slot)
{
	vmc_cardinfo_t *cardinfo;
	cardinfo = &mcman_vmc_cardinfo[slot];
	if (cardinfo->opened) {
		iomanX_close(cardinfo->fd);
	}
	memset(cardinfo, 0, sizeof(vmc_cardinfo_t));
	cardinfo->fd = -1;

	mcman_invhandles(0, slot);
	mcman_clearcache(0, slot);
	memset(&mcman_devinfos[0][slot], 0, sizeof(MCDevInfo));
}

static int mcman_iomanx_backing_validate(int slot, int check_mounted)
{
	vmc_cardinfo_t *cardinfo;

	if (slot < 0 || slot >= MCMAN_MAXSLOT) {
		return -EOVERFLOW;
	}

	cardinfo = &mcman_vmc_cardinfo[slot];

	if (check_mounted) {
		if (cardinfo->mounted == 0) {
			return -ENXIO;
		}
	}
	return 0;
}

int mcman_iomanx_backing_ps1(int port, int slot)
{
    (void)port;
    return mcman_iomanx_backing_validate(slot, 1) == 0 &&
           mcman_vmc_cardinfo[slot].pagesize == 128;
}

int mcman_iomanx_backing_mount(int port, int slot, const char *filename)
{
	int fd;
	int cardsize;
	int r;
	vmc_cardinfo_t *cardinfo;

	(void)port;

	r = mcman_iomanx_backing_validate(slot, 0);
	if (r < 0) return r;

	/* Replacing a mounted card must preserve dirty cache and wrapper metadata. */
	if (mcman_vmc_cardinfo[slot].mounted) {
		r = mcman_iomanx_backing_umount(port, slot);
		if (r < 0) return r;
	}
	mcman_iomanx_backing_clear_slot(slot);
	r = -EINVAL;

	cardinfo = &mcman_vmc_cardinfo[slot];

	fd = iomanX_open(filename, FIO_O_RDWR, 0);
	if (fd < 0) {
		// Propogate open error
		r = fd;
		goto cleanup;
	}
	cardinfo->fd = fd;
	cardinfo->opened = 1;

	cardsize = iomanX_lseek(fd, 0, FIO_SEEK_END);
	/* cardinfo->cardsize is total pages; set after superblock validation. */
	iomanX_lseek(fd, 0, FIO_SEEK_SET);

	// Check superblock for correct parameters
	{
		MCDevInfo superblock;
		int read_result;
		int total_pages;

		read_result = iomanX_read(fd, &superblock, sizeof(superblock));
		if (read_result != sizeof(superblock)) {
			if (read_result >= 0) {
				r = -EINVAL;
			}
			else {
				r = read_result;
			}
			goto cleanup;
		}
		/* Container signatures and lengths identify PS1 cards independently of
		 * extension. Each wrapper holds the same 128 KiB card data. */
		{
			const u8 *header = (const u8 *)&superblock;
			int offset = -1;
			u8 magic[2];
			if (cardsize == 131072) offset = 0;
			else if (cardsize == 131136 && !strncmp((const char *)header, "VgsM", 4)) offset = 64;
			else if (cardsize == 131200 && header[0] == 0 && !strncmp((const char *)header + 1, "PMV", 3) && header[4] == 128) offset = 128;
			else if (cardsize == 134976 && !strncmp((const char *)header, "123-456-STD", 11)) offset = 3904;
			if (offset >= 0) {
				if (iomanX_lseek(fd, offset, FIO_SEEK_SET) != offset || iomanX_read(fd, magic, 2) != 2 || magic[0] != 'M' || magic[1] != 'C') goto cleanup;
				cardinfo->data_offset = offset;
				cardinfo->pagesize = 128;
				cardinfo->blocksize = 64;
				cardinfo->cardsize = 1024;
				cardinfo->mounted = 1;
				r = mcman_setPS1devinfos(port, slot);
				if (r != sceMcResSucceed) r = -EIO;
				goto cleanup;
			}
		}
		// Check magic
		if (strncmp(superblock.magic, SUPERBLOCK_MAGIC, 28) != 0) {
			r = -EINVAL;
			goto cleanup;
		}
		// Check card type
		if (superblock.cardtype != sceMcTypePS2) {
			r = -EINVAL;
			goto cleanup;
		}
		/* MCMAN uses 1 KiB cache clusters and at most sixteen per erase block.
		 * The superblock's data-page size excludes any 16-byte ECC spare. */
		if (superblock.pagesize != 512 || superblock.pages_per_cluster != 2 ||
		    !superblock.clusters_per_card || superblock.clusters_per_card > 0x3fffffff ||
		    !superblock.blocksize || superblock.blocksize > 32 || (superblock.blocksize % 2)) goto cleanup;
		total_pages = superblock.pages_per_cluster * superblock.clusters_per_card;
		if (total_pages % superblock.blocksize) goto cleanup;
		/* Divide first so a malformed superblock cannot overflow the size check. */
		if (cardsize > 0 && cardsize % 528 == 0 && cardsize / 528 == total_pages) cardinfo->has_ecc = 1;
		else if (cardsize > 0 && cardsize % 512 == 0 && cardsize / 512 == total_pages) cardinfo->has_ecc = 0;
		else goto cleanup;

		// Retrieve rest of info
		cardinfo->pagesize = superblock.pagesize;
		cardinfo->blocksize = superblock.blocksize;
		cardinfo->flags = superblock.cardflags;
		cardinfo->cardsize = total_pages;
		cardinfo->mounted = 1;
	}

	mcman_probePS2Card(port, slot);
	if (McGetFormat(port, slot) > 0) {
		r = 0; // Success
		goto cleanup;
	}
	if (McGetFormat(port, slot) < 0) {
		r = -EIO;
		goto cleanup;
	}

cleanup:
	if (r < 0) {
		mcman_iomanx_backing_clear_slot(slot);
	}
	return r;
}

int mcman_iomanx_backing_umount(int port, int slot)
{
	int r;

	(void)port;

	r = mcman_iomanx_backing_validate(slot, 1);
	if (r < 0) {
		goto cleanup;
	}

	r = McFlushCache(port, slot);
	if (r < 0 || mcman_iomanx_backing_commit(port, slot)) return -EIO;
	mcman_iomanx_backing_clear_slot(slot);

cleanup:
	return r;
}

int mcman_iomanx_backing_getcardspec(int port, int slot, s16 *pagesize, u16 *blocksize, int *cardsize, u8 *flags)
{
	int r;
	vmc_cardinfo_t *cardinfo;

	(void)port;

	r = mcman_iomanx_backing_validate(slot, 1);
	if (r < 0) {
		return 1;
	}

	cardinfo = &mcman_vmc_cardinfo[slot];

	if (pagesize) {
		*pagesize = cardinfo->pagesize;
	}

	if (blocksize) {
		*blocksize = cardinfo->blocksize;
	}

	if (cardsize) {
		*cardsize = cardinfo->cardsize;
	}

	if (flags) {
		*flags = cardinfo->flags;
	}

	return 0;
}

int mcman_iomanx_backing_erase(int port, int slot, int page)
{
	int r;
	vmc_cardinfo_t *cardinfo;

	(void)port;

	r = mcman_iomanx_backing_validate(slot, 1);
	if (r < 0) {
		return 1;
	}

	cardinfo = &mcman_vmc_cardinfo[slot];
	if (page < 0 || page >= cardinfo->cardsize) return 1;

	{
		char buf[544];
		int effective_page_size;

		memset(buf, ((cardinfo->flags & CF_ERASE_ZEROES) != 0) ? 0x0 : 0xFF, sizeof(buf));
		effective_page_size = (cardinfo->pagesize + (cardinfo->has_ecc ? 0x10 : 0));
		if (iomanX_lseek(cardinfo->fd, cardinfo->data_offset + page * effective_page_size, FIO_SEEK_SET) < 0) {
			printf("vmcman: backing seek failed page=%d size=%d\n", page, effective_page_size);
			return 1;
		}
		if (iomanX_write(cardinfo->fd, buf, effective_page_size) != effective_page_size) {
			printf("vmcman: erase write failed page=%d size=%d\n", page, effective_page_size);
			return 1;
		}
	}

	cardinfo->dirty = 1;
	return 0;
}

int mcman_iomanx_backing_write(int port, int slot, int page, void *pagebuf, void *eccbuf)
{
	vmc_cardinfo_t *cardinfo;
	u8 sector[528];
	int length, offset;
	(void)port;
	if (mcman_iomanx_backing_validate(slot, 1) < 0) return 1;
	cardinfo = &mcman_vmc_cardinfo[slot];
	if (page < 0 || page >= cardinfo->cardsize) return 1;
	length = cardinfo->pagesize + (cardinfo->has_ecc ? 16 : 0);
	offset = cardinfo->data_offset + page * length;
	if (!pagebuf && !eccbuf) return 0;
	if (pagebuf) memcpy(sector, pagebuf, cardinfo->pagesize);
	else {
		if (!cardinfo->has_ecc) return 0;
		if (iomanX_lseek(cardinfo->fd, offset, FIO_SEEK_SET) != offset ||
		    iomanX_read(cardinfo->fd, sector, cardinfo->pagesize) != cardinfo->pagesize) return 1;
	}
	if (cardinfo->has_ecc) {
		/* Preserve caller spare metadata (or existing spare bytes for a data-only
		 * update), but always derive the ECC bytes from the data being written. */
		if (eccbuf) memcpy(sector + 512, eccbuf, 16);
		else if (iomanX_lseek(cardinfo->fd, offset + 512, FIO_SEEK_SET) != offset + 512 ||
		         iomanX_read(cardinfo->fd, sector + 512, 16) != 16) return 1;
		for (int i = 0; i < 4; i++) McDataChecksum(sector + 128 * i, sector + 512 + 3 * i);
	}
	if (iomanX_lseek(cardinfo->fd, offset, FIO_SEEK_SET) != offset ||
	    iomanX_write(cardinfo->fd, sector, length) != length) return 1;
	cardinfo->dirty = 1;
	return 0;
}

int mcman_iomanx_backing_read(int port, int slot, int page, void *pagebuf, void *eccbuf)
{
	int r;
	vmc_cardinfo_t *cardinfo;

	(void)port;

	r = mcman_iomanx_backing_validate(slot, 1);
	if (r < 0) {
		return 1;
	}

	cardinfo = &mcman_vmc_cardinfo[slot];
	if (page < 0 || page >= cardinfo->cardsize) return 1;

	{
		int pagesize;
		int effective_page_size;

		pagesize = cardinfo->pagesize;

		effective_page_size = (cardinfo->pagesize + (cardinfo->has_ecc ? 0x10 : 0));
		if (iomanX_lseek(cardinfo->fd, cardinfo->data_offset + page * effective_page_size, FIO_SEEK_SET) < 0) {
			printf("vmcman: backing seek failed page=%d size=%d\n", page, effective_page_size);
			return 1;
		}
		if (pagebuf != NULL) {
			if (iomanX_read(cardinfo->fd, pagebuf, cardinfo->pagesize) != cardinfo->pagesize) {
				printf("vmcman: page read failed page=%d\n", page);
				return 1;
			}
		}
		else {
			iomanX_lseek(cardinfo->fd, cardinfo->pagesize, FIO_SEEK_CUR);
		}

		if (cardinfo->has_ecc) {
			if (eccbuf != NULL) {
				if (iomanX_read(cardinfo->fd, eccbuf, 16) != 16) {
					printf("vmcman: ecc read failed page=%d\n", page);
					return 1;
				}
			}
			else {
				iomanX_lseek(cardinfo->fd, 16, FIO_SEEK_CUR);
			}
		} else if (pagebuf != NULL && eccbuf != NULL) {
			int i;
			int ecc_count;
			u8 *p_page, *p_ecc;

			// Make our own ECC

			memset(eccbuf, ((cardinfo->flags & CF_ERASE_ZEROES) != 0) ? 0x0 : 0xFF, 16);
			p_page = pagebuf;
			p_ecc = eccbuf;

			i = 0;	//s1
			do {
				if (pagesize < 0)
					ecc_count = (pagesize + 0x7f) >> 7;
				else
					ecc_count = pagesize >> 7;

				if (i >= ecc_count)
					break;

				McDataChecksum(p_page, p_ecc);

				p_ecc = (void *)((u8 *)p_ecc + 3);
				p_page = (void *)((u8 *)p_page + 128);
				i++;
			} while (1);
		}
	}

	return 0;
}
/* Complete a filesystem flush while the driver semaphore is held. */
int mcman_iomanx_backing_commit(int port, int slot)
{
	vmc_cardinfo_t *cardinfo;
	if (mcman_iomanx_backing_validate(slot, 1) < 0) return 0;
	cardinfo = &mcman_vmc_cardinfo[slot];
	if (!cardinfo->dirty) return 0;
	if (cardinfo->data_offset == 128) {
		if (vmc_vmp_sign(cardinfo->fd) < 0) return 1;
	} else if (cardinfo->data_offset == 3904) {
		u8 directory[128], modes[15], links[15];
		for (int i = 0; i < 15; i++) {
			if (mcman_iomanx_backing_read(port, slot, i + 1, directory, NULL)) return 1;
			modes[i] = directory[0]; links[i] = directory[8];
		}
		if (iomanX_lseek(cardinfo->fd, 22, FIO_SEEK_SET) != 22 || iomanX_write(cardinfo->fd, modes, 15) != 15 ||
		    iomanX_lseek(cardinfo->fd, 38, FIO_SEEK_SET) != 38 || iomanX_write(cardinfo->fd, links, 15) != 15) return 1;
	}
	cardinfo->dirty = 0;
	return 0;
}

#endif
