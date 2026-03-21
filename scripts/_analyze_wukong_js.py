import gzip
import re

PATH = "wukong_index.js"


def main() -> None:
    raw = gzip.open(PATH, "rb").read().decode("utf-8", "replace")
    print("decoded len", len(raw))
    words = ["invite", "Invite", "邀请", "invitation", "inviteCode", "wukong", "lippi", "api.dingtalk"]
    for w in words:
        c = raw.count(w) if not w.isascii() else raw.lower().count(w.lower())
        print(w, "->", c)
    urls = set(re.findall(r"https?://[a-zA-Z0-9._/?#&=%-]+", raw))
    ding = [u for u in urls if "ding" in u.lower()][:50]
    for u in sorted(ding):
        print("url:", u[:160])


if __name__ == "__main__":
    main()
