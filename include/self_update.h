#ifndef WLE_SELF_UPDATE_H
#define WLE_SELF_UPDATE_H

/* Keep release metadata, ancestry checks and package downloads on one fork. */
#define SELF_UPDATE_REPOSITORY "saildot4k/Launchstation"
#define SELF_UPDATE_API_PATH "/repos/" SELF_UPDATE_REPOSITORY

#ifdef DS34
#define SELF_UPDATE_FOLDER "APP_LAUNCHSTATION-DS"
#define SELF_UPDATE_ELF "LAUNCHSTATION-DS.ELF"
#else
#define SELF_UPDATE_FOLDER "APP_LAUNCHSTATION"
#define SELF_UPDATE_ELF "LAUNCHSTATION.ELF"
#endif
#define SELF_UPDATE_ASSET SELF_UPDATE_FOLDER ".psu"

int selfUpdateExtractPsu(const char *package, const char *stage, int size);
int selfUpdateExtractPsuSidecar(const char *package, const char *name,
                                const char *stage, int size);

/* Refresh metadata from the same verified package, retaining the boot filename. */
int selfUpdateExtractPsuTitle(const char *package, const char *stage, int size,
                              const char *boot_leaf);

int selfUpdateInstall(const char *ca_path, const char *expected_sha256, char *result, int result_size);

#endif
