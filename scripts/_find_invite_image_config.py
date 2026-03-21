import gzip
import re

PATH = "wukong_office.js.gz"


def main() -> None:
    d = gzip.open(PATH, "rb").read().decode("utf-8", "replace")
    # hero invite: look for wk-hero and preceding const
    i = d.find("wk-hero-invite-img")
    chunk = d[max(0, i - 2500) : i]
    print("--- chunk before wk-hero-invite-img (tail 2000 chars) ---")
    print(chunk[-2000:])


if __name__ == "__main__":
    main()
