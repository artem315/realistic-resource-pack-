"""Compile every program of the shader pack with glslangValidator.

Includes are resolved like Iris/OptiFine do ("/lib/x.glsl" = relative to shaders/).
Each program is compiled with the default options and once more with every boolean
option switched off, for all dimensions (main, world-1, world1).

    python tools/check_shaders.py [--quick]
"""
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shaderpack", "shaders")
INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"', re.M)


def expand(path, seen=None):
    seen = seen or set()
    src = open(path).read()

    def rep(m):
        inc = m.group(1)
        p = os.path.join(ROOT, inc.lstrip("/")) if inc.startswith("/") else os.path.join(os.path.dirname(path), inc)
        if p in seen:
            return ""
        seen.add(p)
        return expand(p, seen)
    return INCLUDE.sub(rep, src)


def boolean_options():
    s = open(os.path.join(ROOT, "lib", "settings.glsl")).read()
    return re.findall(r"^#define (\w+)\s*(?://.*)?$", s, re.M)


def compile_src(src, stage):
    with tempfile.NamedTemporaryFile("w", suffix="." + stage, delete=False) as f:
        f.write(src)
        name = f.name
    r = subprocess.run(["glslangValidator", "-S", stage, name], capture_output=True, text=True)
    os.remove(name)
    return r.returncode, r.stdout + r.stderr


def variants(src, options):
    yield "default", src
    for o in options:
        yield f"-{o}", re.sub(rf"^#define {o}\b.*$", f"// #undef {o}", src, flags=re.M)


def main():
    quick = "--quick" in sys.argv
    options = [] if quick else boolean_options()
    jobs = []
    for folder in ("", "world-1", "world1"):
        d = os.path.join(ROOT, folder)
        for f in sorted(os.listdir(d)):
            if not f.endswith((".vsh", ".fsh")):
                continue
            stage = "vert" if f.endswith(".vsh") else "frag"
            src = expand(os.path.join(d, f))
            # settings are included after #version: expand already inlined them
            for vname, vsrc in variants(src, options):
                jobs.append((os.path.join(folder, f), vname, vsrc, stage))
    failures = []
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        for (name, vname, _, _), (code, out) in zip(jobs, ex.map(lambda j: compile_src(j[2], j[3]), jobs)):
            if code != 0:
                failures.append((name, vname, out))
    seen = set()
    for name, vname, out in failures:
        key = out.split("\n", 3)[1] if "\n" in out else out
        if key in seen:
            continue
        seen.add(key)
        print(f"--- {name} [{vname}]")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:2000])
    print(f"{len(jobs)} compilations, {len(failures)} failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
