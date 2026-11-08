"""Check the installed HTTPS configuration and compiled Mbed TLS archives.

Usage: check_https_tls.py <ee-gcc> <ee-nm> [dependency-directory]
Run after build_https_tls.sh; no target code is executed on the host.
"""
from pathlib import Path
import re
import subprocess
import sys


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    compiler, nm = sys.argv[1:3]
    root = Path(__file__).resolve().parents[1]
    deps = Path(sys.argv[3]) if len(sys.argv) == 4 else root / ".https-deps"
    result = subprocess.run(
        [compiler, "-dM", "-E", "-x", "c", "-I" + str(deps / "include"), "-"],
        input="#include <mbedtls/build_info.h>\n", text=True,
        capture_output=True, check=True,
    )
    macros = set(re.findall(r"^#define (\w+)", result.stdout, re.M))
    required = {
        "MBEDTLS_SSL_CLI_C", "MBEDTLS_SSL_TLS_C",
        "MBEDTLS_SSL_PROTO_TLS1_2", "MBEDTLS_SSL_PROTO_TLS1_3",
        "MBEDTLS_SSL_SERVER_NAME_INDICATION", "MBEDTLS_X509_CRT_PARSE_C",
        "MBEDTLS_HAVE_TIME", "MBEDTLS_HAVE_TIME_DATE", "MBEDTLS_PEM_PARSE_C",
        "MBEDTLS_KEY_EXCHANGE_ECDHE_RSA_ENABLED",
        "MBEDTLS_KEY_EXCHANGE_ECDHE_ECDSA_ENABLED",
        "MBEDTLS_SSL_TLS1_3_KEY_EXCHANGE_MODE_EPHEMERAL_ENABLED",
        "MBEDTLS_RSA_C", "MBEDTLS_ECDSA_C", "MBEDTLS_PKCS1_V15",
        "MBEDTLS_PKCS1_V21", "MBEDTLS_X509_RSASSA_PSS_SUPPORT",
        "MBEDTLS_ECP_DP_SECP256R1_ENABLED", "MBEDTLS_ECP_DP_SECP384R1_ENABLED",
        "MBEDTLS_ECP_DP_SECP521R1_ENABLED", "MBEDTLS_ECP_DP_CURVE25519_ENABLED",
        "MBEDTLS_AES_C", "MBEDTLS_GCM_C", "MBEDTLS_CHACHAPOLY_C",
        "MBEDTLS_SHA256_C", "MBEDTLS_SHA384_C", "MBEDTLS_SHA512_C",
        "MBEDTLS_CTR_DRBG_C", "MBEDTLS_ENTROPY_C",
        "MBEDTLS_PLATFORM_MS_TIME_ALT", "MBEDTLS_NO_PLATFORM_ENTROPY",
        "MBEDTLS_ENTROPY_HARDWARE_ALT", "MBEDTLS_ERROR_C",
    }
    # Check every disabled feature against the effective upstream configuration,
    # including config adjustments, rather than just reading our source header.
    profile = (root / "include/https_mbedtls_config.h").read_text()
    disabled = set(re.findall(r"^#undef (\w+)", profile, re.M))
    assert not required - macros, f"Missing HTTPS features: {sorted(required - macros)}"
    assert not disabled & macros, f"Unwanted TLS features: {sorted(disabled & macros)}"
    assert "MBEDTLS_X509_REMOVE_INFO" not in macros, "Keep certificate diagnostics"

    symbols = set()
    for name in ("mbedtls", "mbedx509", "mbedcrypto"):
        result = subprocess.run(
            [nm, "--defined-only", str(deps / "lib" / f"lib{name}.a")],
            text=True, capture_output=True, check=True,
        )
        symbols.update(re.findall(r"^\s*[0-9a-fA-F]+\s+[A-Za-z]\s+(\w+)$",
                                  result.stdout, re.M))
    for name in ("mbedtls_ssl_handshake_client_step",
                 "mbedtls_ssl_tls13_handshake_client_step",
                 "mbedtls_ssl_set_hostname", "mbedtls_ssl_get_verify_result",
                 "mbedtls_x509_crt_verify", "mbedtls_x509_crt_verify_info",
                 "mbedtls_sha256", "mbedtls_rsa_rsassa_pss_verify",
                 "mbedtls_ecdsa_read_signature", "mbedtls_gcm_crypt_and_tag",
                 "mbedtls_chachapoly_encrypt_and_tag"):
        assert name in symbols, f"Missing compiled HTTPS support: {name}"
    unused = re.compile(
        r"mbedtls_(?:aria_|camellia_|des[3_]|dhm_|ecjpake_|md5_|ripemd160_|"
        r"sha3_|lms_|ssl_cookie_|ssl_ticket_|ssl_cache_|"
        r"ssl_handshake_server_step|ssl_tls13_handshake_server_step|"
        r"x509write_|x509_csr_|pk_write_|pem_write_)")
    unexpected = sorted(name for name in symbols if unused.match(name))
    assert not unexpected, f"Unused TLS code still compiled: {unexpected}"
    print("PASS: matching HTTPS headers/archives retain authenticated TLS 1.2/1.3 "
          "and omit unused TLS features")


if __name__ == "__main__":
    main()
