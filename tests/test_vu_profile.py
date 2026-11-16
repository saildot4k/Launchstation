"""Validate bounded profiling storage, Count wrapping and rolling quantiles."""
from pathlib import Path
import os
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
#include <stdint.h>
#include "dash_profile.h"
static uint32_t counter;
uint32_t dashProfileHostCounter(void) { return counter; }
int main(void) {
 dashProfileReset();
 for (unsigned i=1;i<=200;i++) {counter=i;dashProfileEnd(DASH_PROF_FRAME,0);}
 counter=4;dashProfileEnd(DASH_PROF_TUNNEL,0xfffffff0u);
 dashProfileEnd((enum DashProfileSlot)-1,0);
 dashProfileReport();
 dashProfileReset();dashProfileReport();
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="vu-profile-") as folder:
 folder=Path(folder);(folder/"test.c").write_text(code)
 subprocess.run([os.environ.get("CC","cc"),"-std=c11","-Wall","-Wextra","-Werror","-DDASH_PROFILE=1",
  "-I",str(root/"include"),str(folder/"test.c"),str(root/"src/dash_profile.c"),"-o",str(folder/"test")],check=True)
 result=subprocess.check_output([str(folder/"test")],text=True)
 assert "slot=frame-build calls=200 mean=100 max=200 p50=136 p95=194 samples=128" in result,result
 assert "slot=tunnel calls=1 mean=20 max=20 p50=20 p95=20 samples=1" in result,result
 assert result.count("[dash-profile]")==2,result
 print("PASS: real profiling recorder, fixed 128-sample window, reset, Count wrap and quantiles")
