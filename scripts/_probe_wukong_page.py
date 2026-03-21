import re
import urllib.request

URL = "https://n.dingtalk.com/dingding/h5-wukong-launch/index.html"


def main() -> None:
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        },
    )
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    print("length", len(raw))
    for pat in ["邀请", "invite", "code", "INVITE", "wukong", "悟空"]:
        c = raw.lower().count(pat.lower()) if pat.isascii() else raw.count(pat)
        print(pat, "count", c)
    for m in re.finditer(r".{0,80}(邀请码|inviteCode|invite_code|invite-code).{0,80}", raw, re.I):
        print("match:", m.group(0).replace("\n", " ")[:200])
    # script src
    for m in re.finditer(r'<script[^>]+src="([^"]+)"', raw):
        print("script:", m.group(1)[:120])


if __name__ == "__main__":
    main()
