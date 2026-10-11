"""Build the resource pack.

    python tools/build.py                 # 256x into the repository root (assets/...)
    python tools/build.py --res 128       # lighter 128x version
    python tools/build.py --only stone ores --res 256
    python tools/build.py --zip dist/Mellow-Realistic-PBR-256x.zip

Textures are written to assets/minecraft/textures/block as <name>.png,
<name>_n.png and <name>_s.png (labPBR 1.3).
"""
import argparse
import json
import os
import sys
import time
import traceback
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pbrlib  # noqa: E402

MODULES = ["recipes_natural", "recipes_wood", "recipes_plants", "recipes_built", "recipes_colored"]


def load_recipes(res):
    pbrlib.set_resolution(res)
    import importlib
    recipes = {}
    for mod in MODULES:
        try:
            m = importlib.import_module(mod)
        except ModuleNotFoundError as e:
            if e.name == mod:
                continue
            raise
        for k, fn in m.R.items():
            recipes[f"{mod}.{k}"] = fn
    return recipes


def run_recipe(key, res, out_dir):
    recipes = load_recipes(res)
    fn = recipes[key]
    t = time.time()
    result = fn()
    names = []
    for name, mat in result.items():
        opts = {}
        if isinstance(mat, tuple) and mat[0] == "anim":
            pbrlib.save_animated(mat[1], out_dir, name, frametime=mat[2])
        else:
            if isinstance(mat, tuple) and mat[0] == "opts":
                opts, mat = mat[1], mat[2]
            pbrlib.save(mat, out_dir, name, **opts)
        names.append(name)
    return key, names, time.time() - t


def write_meta(root, res):
    meta = {
        "pack": {
            "description": f"§6Mellow Realistic PBR §7{res}x\n§8labPBR 1.3 • POM • CC0 photo sources",
            "pack_format": 15,
            "supported_formats": {"min_inclusive": 15, "max_inclusive": 999},
            "min_format": 15,
            "max_format": 999,
        }
    }
    with open(os.path.join(root, "pack.mcmeta"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")


def make_icon(root):
    """pack.png: four lit sample blocks."""
    import preview
    from PIL import Image
    names = [("grass_block_top", (0.47, 0.75, 0.35)), ("oak_log_top", None), ("cobblestone", None),
             ("diamond_ore", None)]
    if not all(os.path.exists(os.path.join(preview.BLOCK, n + ".png")) for n, _ in names):
        return
    icon = Image.new("RGB", (256, 256))
    for i, (n, tint) in enumerate(names):
        icon.paste(preview.shade(n, 128, tiles=1, tint=tint), ((i % 2) * 128, (i // 2) * 128))
    icon.save(os.path.join(root, "pack.png"), optimize=True)


def make_zip(root, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for extra in ("pack.mcmeta", "pack.png", "LICENSE", "CREDITS.md"):
            p = os.path.join(root, extra)
            if os.path.exists(p):
                z.write(p, extra)
        for dp, _, files in os.walk(os.path.join(root, "assets")):
            for f in sorted(files):
                full = os.path.join(dp, f)
                z.write(full, os.path.relpath(full, root))
    print("zip:", path, f"{os.path.getsize(path) / 1e6:.1f} MB")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=256)
    p.add_argument("--out", default=ROOT, help="pack root (default: repository root)")
    p.add_argument("--only", nargs="*", help="recipe names (substring match)")
    p.add_argument("--jobs", type=int, default=os.cpu_count())
    p.add_argument("--zip", help="also write a zip of the pack here")
    p.add_argument("--clean", action="store_true", help="delete existing block textures first")
    args = p.parse_args()

    out_dir = os.path.join(args.out, "assets", "minecraft", "textures", "block")
    if args.clean and os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))
    os.makedirs(out_dir, exist_ok=True)

    keys = list(load_recipes(args.res))
    if args.only:
        keys = [k for k in keys if any(o in k for o in args.only)]

    # make sure every source is downloaded before forking workers
    import fetch  # noqa: F401
    total = 0
    failed = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_recipe, k, args.res, out_dir): k for k in keys}
        for fu in as_completed(futs):
            k = futs[fu]
            try:
                key, names, dt = fu.result()
                total += len(names)
                print(f"[{dt:5.1f}s] {key}: {', '.join(names)}")
            except Exception:
                failed.append(k)
                print(f"FAILED {k}")
                traceback.print_exc()
    write_meta(args.out, args.res)
    make_icon(args.out)
    print(f"{total} textures in {time.time() - t0:.0f}s, {len(failed)} failed")
    if args.zip:
        make_zip(args.out, args.zip)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
