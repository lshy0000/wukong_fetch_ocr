import urllib.request

URL = "https://yunlin-www.oss-cn-hangzhou.aliyuncs.com/dingding2026/config.yaml?rnd=0.5"


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    keywords = ["邀请", "invite", "Invite", "inviteCode", "wukong", "悟空", "内测"]
    for kw in keywords:
        if kw.lower() in text.lower() or kw in text:
            print("contains:", kw)
    for line in text.splitlines():
        low = line.lower()
        if "邀请" in line or "invite" in low or "wukong" in low or "悟空" in line:
            print(line[:240])


if __name__ == "__main__":
    main()
