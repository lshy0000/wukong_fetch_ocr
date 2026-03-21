"""One-off probe: search homepage HTML for invite-related strings."""
import re
import urllib.request

URL = "https://www.dingtalk.com/"


def main() -> None:
    raw = urllib.request.urlopen(URL, timeout=30).read().decode("utf-8", "replace")
    print("length", len(raw))
    keys = ["邀请", "invite", "Invite", "wukong", "悟空", "inviteCode", "__NEXT_DATA__"]
    for k in keys:
        if k in raw:
            print("found substring:", k)
    for m in re.finditer(r".{0,60}(邀请码|inviteCode|invite-code).{0,60}", raw, re.I):
        s = m.group(0).replace("\n", " ")
        print("match:", s[:180])
    idx = raw.lower().find("wukong")
    if idx >= 0:
        snippet = raw[max(0, idx - 120) : idx + 200]
        print("wukong context:", snippet.replace("\n", " ")[:320])


if __name__ == "__main__":
    main()
