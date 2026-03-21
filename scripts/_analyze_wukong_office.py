import gzip
import re

PATH = "wukong_office.js.gz"


def main() -> None:
    data = gzip.open(PATH, "rb").read().decode("utf-8", "replace")
    print("len", len(data))
    print("invite in lower:", "invite" in data.lower())
    print("邀请 in data:", "邀请" in data)
    urls = re.findall(r"https?://[^\s\"'<>]+", data)
    print("url count", len(urls))
    for u in sorted(set(urls))[:40]:
        print(u[:150])


def hero_invite() -> None:
    data = gzip.open(PATH, "rb").read().decode("utf-8", "replace")
    key = "wk-hero-invite"
    i = data.find(key)
    if i < 0:
        print("no hero invite block")
        return
    print(data[i : i + 1200])


def invite_snippets() -> None:
    data = gzip.open(PATH, "rb").read().decode("utf-8", "replace")
    for m in re.finditer(r".{0,40}invite.{0,100}", data, re.I):
        s = m.group(0).replace("\n", " ")
        if len(s) > 200:
            s = s[:200] + "..."
        print(s)


if __name__ == "__main__":
    main()
    print("--- invite snippets ---")
    invite_snippets()
    print("--- hero invite block ---")
    hero_invite()
