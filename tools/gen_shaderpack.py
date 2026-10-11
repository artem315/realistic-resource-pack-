"""Generate the thin program wrappers of the shader pack (shaderpack/shaders/*.vsh|fsh).

Every Iris/OptiFine program is a 4-line file that selects a body in program/ with a
#define; the same wrappers are emitted in world-1/ (Nether) and world1/ (End).

    python tools/gen_shaderpack.py [--zip build/Realistic-PBR-Shaders.zip]
"""
import os
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shaderpack", "shaders")

# program name: (body, define, render targets of the fragment stage)
PROGRAMS = {
    "gbuffers_basic":        ("gbuffers", "GB_BASIC", "0"),
    "gbuffers_textured":     ("gbuffers", "GB_PARTICLES", "0"),
    "gbuffers_textured_lit": ("gbuffers", "GB_PARTICLES", "0"),
    "gbuffers_terrain":      ("gbuffers", "GB_TERRAIN", "0,1,2,3"),
    "gbuffers_block":        ("gbuffers", "GB_BLOCK", "0,1,2,3"),
    "gbuffers_entities":     ("gbuffers", "GB_ENTITIES", "0,1,2,3"),
    "gbuffers_hand":         ("gbuffers", "GB_HAND", "0,1,2,3"),
    "gbuffers_water":        ("gbuffers", "GB_WATER", "0,6"),
    "gbuffers_hand_water":   ("gbuffers", "GB_HAND_WATER", "0,6"),
    "gbuffers_weather":      ("gbuffers", "GB_WEATHER", "0"),
    "gbuffers_beaconbeam":   ("gbuffers", "GB_EMISSIVE", "0"),
    "gbuffers_spidereyes":   ("gbuffers", "GB_EMISSIVE", "0"),
    "gbuffers_armor_glint":  ("gbuffers", "GB_GLINT", "0"),
    "gbuffers_damagedblock": ("gbuffers", "GB_DAMAGED", "0"),
    "gbuffers_skybasic":     ("sky", "SKY_BASIC", "0"),
    "gbuffers_skytextured":  ("sky", "SKY_TEXTURED", "0"),
    "gbuffers_clouds":       ("sky", "SKY_CLOUDS", "0"),
    "shadow":                ("shadow", "SHADOW_PASS", "0"),
    "deferred":              ("deferred", "DEFERRED_PASS", "0"),
    "composite":             ("composite", "COMPOSITE_PASS", "0"),
    "final":                 ("final", "FINAL_PASS", None),
}

DIMENSIONS = {"": None, "world-1": "DIM_NETHER", "world1": "DIM_END"}


def wrapper(body, define, targets, stage, dim):
    lines = ["#version 330 compatibility", f"#define {stage}", f"#define {define}"]
    if dim:
        lines.append(f"#define {dim}")
    if stage == "FRAGMENT" and targets is not None:
        lines.append(f"/* RENDERTARGETS: {targets} */")
    lines.append(f'#include "/program/{body}.glsl"')
    return "\n".join(lines) + "\n"


def main():
    n = 0
    for folder, dim in DIMENSIONS.items():
        d = os.path.join(ROOT, folder)
        os.makedirs(d, exist_ok=True)
        for name, (body, define, targets) in PROGRAMS.items():
            for ext, stage in (("vsh", "VERTEX"), ("fsh", "FRAGMENT")):
                with open(os.path.join(d, f"{name}.{ext}"), "w") as f:
                    f.write(wrapper(body, define, targets, stage, dim))
                n += 1
    print(f"{n} wrappers written")
    if "--zip" in sys.argv:
        out = sys.argv[sys.argv.index("--zip") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        base = os.path.dirname(ROOT)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, _, files in os.walk(ROOT):
                for f in sorted(files):
                    full = os.path.join(dp, f)
                    z.write(full, os.path.relpath(full, base))
            for extra in ("README.md", "LICENSE"):
                p = os.path.join(base, extra)
                if os.path.exists(p):
                    z.write(p, extra)
        print("zip:", out, f"{os.path.getsize(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
