r"""
Makes web-sized copies of photos and videos for the site.

    python tools\make_media.py

Reads from "Pictures Videos\", writes to "media\". Originals are never touched.

  photos  (.jpg .png .heic)  ->  .jpg, longest side 1800 px, with a 600 px thumb
  videos  (.mov .mp4)        ->  .mp4 (H.264, plays in every browser), max 1080p,
                                 plus a .jpg poster frame shown before it plays

Files already converted are skipped, so re-running is quick. Delete a file in
media\ to force it to be rebuilt.

Needs:  pip install pillow pillow-heif imageio-ffmpeg
"""

import os
import re
import subprocess
import sys

from PIL import Image, ImageOps
import pillow_heif
import imageio_ffmpeg

pillow_heif.register_heif_opener()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "Pictures Videos")
OUT = os.path.join(HERE, "media")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

PHOTO = {".jpg", ".jpeg", ".png", ".heic"}
VIDEO = {".mov", ".mp4"}

# Which files go on the site. Check-Mate: only the ones renamed by hand.
PICK = {
    "chess": ("Check-Mate", [
        "Automatic ChessBoard MK3 Beauty Shot.PNG",
        "Automatic ChessBoard MK3 Corner Shot.PNG",
        "Automatic ChessBoard MK3 Top Shot.PNG",
        "MK3 Open.jpeg",
        "MK3 Open 2.HEIC",
        "MK3 At comp.HEIC",
        "MK3 Decent.mov",
        "MK3 Playing bad.MOV",
        "MK2 Moving.MOV",
        "MK2 Moving Piece.MOV",
    ]),
    "crc": ("CRC", None),   # None = everything in the folder
}

# Short silent loops that autoplay in each project's gallery preview.
#   media file (without .mp4)  :  (start second, length in seconds)
PREVIEWS = {
    "chess/mk3-decent":     (4, 12),
    "crc/cut-swerve-test":  (0, 10),
}


def slug(name):
    base = os.path.splitext(name)[0].lower()
    base = base.replace("automatic chessboard ", "")
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def photo(src, dst):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    full = im.copy()
    full.thumbnail((1800, 1800), Image.LANCZOS)
    full.save(dst + ".jpg", quality=84, optimize=True, progressive=True)
    im.thumbnail((600, 600), Image.LANCZOS)
    im.save(dst + "-thumb.jpg", quality=80, optimize=True, progressive=True)


def video(src, dst):
    subprocess.run([
        FFMPEG, "-y", "-loglevel", "error", "-i", src,
        "-vf", "scale='if(gt(iw,ih),min(1920,iw),-2)':'if(gt(iw,ih),-2,min(1920,ih))'",
        "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
        dst + ".mp4"], check=True)
    subprocess.run([
        FFMPEG, "-y", "-loglevel", "error", "-ss", "1", "-i", dst + ".mp4",
        "-frames:v", "1", "-vf", "scale='min(900,iw)':-2", "-q:v", "4",
        dst + "-poster.jpg"], check=True)


def main():
    for group, (folder, names) in PICK.items():
        root = os.path.join(SRC, folder)
        if names is None:
            files = [os.path.join(dp, f) for dp, _, fs in os.walk(root) for f in sorted(fs)]
        else:
            files = [os.path.join(root, n) for n in names]
        os.makedirs(os.path.join(OUT, group), exist_ok=True)

        for src in files:
            ext = os.path.splitext(src)[1].lower()
            dst = os.path.join(OUT, group, slug(os.path.basename(src)))
            done = dst + (".jpg" if ext in PHOTO else ".mp4")
            if not os.path.isfile(src):
                print("  MISSING  %s" % src)
                continue
            if os.path.isfile(done):
                print("  skip     %s" % os.path.relpath(done, HERE))
                continue
            print("  convert  %s" % os.path.relpath(src, HERE), flush=True)
            if ext in PHOTO:
                photo(src, dst)
            elif ext in VIDEO:
                video(src, dst)

    for name, (start, length) in PREVIEWS.items():
        src = os.path.join(OUT, name + ".mp4")
        dst = os.path.join(OUT, name + "-preview.mp4")
        if os.path.isfile(dst) or not os.path.isfile(src):
            continue
        print("  preview  %s" % os.path.relpath(dst, HERE), flush=True)
        subprocess.run([
            FFMPEG, "-y", "-loglevel", "error", "-ss", str(start), "-t", str(length), "-i", src,
            "-vf", "scale=-2:540", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "30",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], check=True)
        subprocess.run([
            FFMPEG, "-y", "-loglevel", "error", "-i", dst, "-frames:v", "1", "-q:v", "4",
            dst[:-4] + "-poster.jpg"], check=True)
    print("done")


if __name__ == "__main__":
    sys.exit(main())
