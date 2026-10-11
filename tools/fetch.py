"""Download and unpack CC0 source materials from ambientCG (https://ambientcg.com).

Only the maps the generator needs are kept:
Color, NormalDX, Displacement, Roughness, AmbientOcclusion, Metalness, Opacity.
"""
import os
import subprocess
import sys
import time
import zipfile

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "acg")
KEEP = ("Color", "NormalDX", "Displacement", "Roughness", "AmbientOcclusion", "Metalness", "Opacity")


def material_dir(asset_id, quality="1K-JPG"):
    return os.path.join(CACHE, f"{asset_id}_{quality}")


def fetch(asset_id, quality="1K-JPG"):
    out = material_dir(asset_id, quality)
    if os.path.isdir(out) and os.listdir(out):
        return out
    os.makedirs(CACHE, exist_ok=True)
    zpath = out + ".zip"
    url = f"https://ambientcg.com/get?file={asset_id}_{quality}.zip"
    for attempt in range(8):
        r = subprocess.run(["curl", "-sSfL", "--max-time", "600", "-o", zpath, url], capture_output=True)
        if r.returncode == 0 and zipfile.is_zipfile(zpath):
            break
        time.sleep(min(2 ** attempt, 30))
    else:
        raise RuntimeError(f"failed to download {url}: {r.stderr.decode(errors='replace')}")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename
            if any(f"_{k}." in name for k in KEEP) and "/" not in name:
                z.extract(info, out)
    os.remove(zpath)
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(fetch(a))
