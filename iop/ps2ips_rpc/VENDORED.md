# PS2IP socket RPC server

Source: [ps2dev/ps2sdk](https://github.com/ps2dev/ps2sdk), pinned at
[`329e2bb43287e16af16c4dde1c614e2662c24468`](https://github.com/ps2dev/ps2sdk/tree/329e2bb43287e16af16c4dde1c614e2662c24468).

- `ps2ips.c`, `imports.lst`, `irx_imports.h`: `iop/tcpip/tcpips/src/`.
- `ps2ip_rpc.h`: `common/include/ps2ip_rpc.h`, including the fixed-width
  select RPC layout introduced upstream in May 2026.
- `PS2SDK_LICENSE.txt`: upstream `LICENSE` (Academic Free License 2.0).

Original source notices and copyrights are retained.

The PS2BUILD SDK's `ps2ips` target supplies the EE client library. It is not an
IRX artifact. Launchstation builds this server as the separate IOP target
`ps2ips_rpc` and embeds it with `ps2ips_rpc:ps2ips`, retaining the runtime symbols
`ps2ips_irx` / `size_ps2ips_irx`. The standard PS2BUILD target compiles the
corrected [EE client](../../ee_libs/tcpips/VENDORED.md) directly; `ps2ips`
supplies its libc adapter.
The runtime loads this server only for Internet clients, after their IP stack.

Local changes to the upstream server:

1. DNS replies copy the resolved IPv4 bytes rather than the address of the IOP
   pointer; malformed or missing address lists return a lookup failure.
2. A failed `StartThread` deletes the unstarted thread and reports
   `MODULE_NO_RESIDENT_END`, preventing an EE bind to an absent RPC server.
3. `imports.lst` includes `DeleteThread` for that cleanup.
4. UDP receive initializes the sender-address capacity and postpones writing
   the returned address until its overlapping request fields (`ee_addr` and
   `intr_data`) have been consumed. This preserves the destination pointers
   for the received packet and its DMA/reassembly metadata.
5. The shared socket transfer buffer reserves 64 bytes of headroom, covering
   a full 1024-byte payload at every supported alignment.
6. TCP/UDP reads with no payload return cleared receive metadata, preventing
   the EE callback from replaying an earlier read's head/tail into TLS memory.
   Metadata DMA completes before the RPC returns, including on errors and EOF.

`ps2.yaml` provides an isolated PS2BUILD compile check. The root `ps2.yaml`
builds the same source with DNS enabled. The legacy Makefile continues to use
its SDK's matching `ps2ips.irx` / EE client pair.
