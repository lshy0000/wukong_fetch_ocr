import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

URL = "https://gw.alicdn.com/imgextra/i4/O1CN01tWg8PK1qbT2Hrfv4N_!!6000000005514-2-tps-1974-540.png"


def main() -> None:
    b = httpx.get(URL, timeout=30, follow_redirects=True).content
    ROOT.joinpath("_cdn_probe.png").write_bytes(b)
    from PIL import Image

    im = Image.open(ROOT / "_cdn_probe.png")
    print("size", im.size)
    from wukong_invite.ocr_extract import collect_ocr_texts_from_png, pick_invite_candidate

    lines, _ = collect_ocr_texts_from_png(b)
    print("n_lines", len(lines))
    for i, x in enumerate(lines):
        print(i, repr(x))
    print("pick", pick_invite_candidate(lines))


if __name__ == "__main__":
    main()
