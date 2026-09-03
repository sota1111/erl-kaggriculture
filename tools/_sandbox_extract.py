"""Run one notebook code cell in a throwaway directory and report the agent it wrote.

Notebook packaging cells write main.py by four different routes (writefile magic,
agentfile magic, write_text of a source string, base64/zlib blobs). Executing the
cell handles all of them uniformly — but executing someone else's notebook code is
exactly how a competitor's agent ends up loose in this repository, which happened
once. So it runs here: separate process, cwd inside a temp directory, and only
main.py is carried back out.

    python tools/_sandbox_extract.py <cell.py> <workdir>   # prints the agent path
"""
import sys, os, io, runpy, contextlib
from pathlib import Path

cell, workdir = sys.argv[1], sys.argv[2]
src = Path(cell).read_text()
src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(("%", "!")))
os.chdir(workdir)
Path("_cell.py").write_text(src)
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        runpy.run_path("_cell.py", run_name="__main__")
except BaseException:
    pass
for cand in ("main.py", "agent.py", "submission/main.py"):
    p = Path(workdir) / cand
    if p.is_file() and "def agent" in p.read_text():
        print(str(p)); break
