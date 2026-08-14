import hashlib
import json
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import requests


WXPUSHER_SPT = os.environ["WXPUSHER_SPT"]
BILI_COOKIE = os.environ.get("BILI_COOKIE", "")
TEST_PUSH = os.environ.get("TEST_PUSH", "").lower() == "true"

UP_LIST = {
    "影视飓风": "946974",
    "IC一站式服务": "3461580865931962",
    "智视界AI时代": "499440615",
    "泫九AI": "21384754",
}

STATE_FILE = Path("seen.json")

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
if BILI_COOKIE:
    SESSION.headers.update({"Cookie": BILI_COOKIE})


def load_seen():
    if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
        return {}

    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_seen(seen):
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def push(title, content):
    resp = requests.post(
        "https://wxpusher.zjiecode.com/api/send/message/simple-push",
        json={
            "spt": WXPUSHER_SPT,
            "summary": title,
            "content": content,
            "contentType": 2,
        },
        timeout=20,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"WxPusher response: {result}")

    if result.get("code") != 1000:
        raise RuntimeError(f"WxPusher push failed: {result}")


def get_mixin_key():
    SESSION.get("https://www.bilibili.com/", timeout=20)
    resp = SESSION.get(
        "https://api.bilibili.com/x/web-interface/nav",
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    wbi_img = data["data"]["wbi_img"]
    img_key = wbi_img["img_url"].rsplit("/", 1)[1].split(".")[0]
    sub_key = wbi_img["sub_url"].rsplit("/", 1)[1].split(".")[0]
    raw = img_key + sub_key

    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign_wbi(params):
    mixin_key = get_mixin_key()
    params = dict(params)
    params["wts"] = int(time.time())

    clean_params = {}
    for key in sorted(params):
        value = str(params[key])
        value = re.sub(r"[!'()*]", "", value)
        clean_params[key] = value

    query = urlencode(clean_params)
    clean_params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return clean_params


def browser_fingerprint_params():
    # These browser fingerprint fields are commonly present on Bilibili web WBI calls.
    return {
        "dm_img_list": "[]",
        "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
        "dm_cover_img_str": (
            "QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3MgRGlyZWN0M0QxMSB2c181XzB"
            "fcHM1XzApLCBvciBzaW1pbGFy"
        ),
        "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
    }


def fetch_up_videos(uid):
    url = "https://api.bilibili.com/x/space/wbi/arc/search"
    base_params = {
        "mid": uid,
        "pn": 1,
        "ps": 20,
        "order": "pubdate",
        "platform": "web",
        "web_location": 1550101,
    }
    base_params.update(browser_fingerprint_params())

    for attempt in range(1, 4):
        params = sign_wbi(base_params)

        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"Bili API request failed for uid={uid}, attempt={attempt}: {exc}")
            time.sleep(8 + random.random() * 5)
            continue

        data = resp.json()
        if data.get("code") == 0:
            items = data.get("data", {}).get("list", {}).get("vlist", [])
            print(f"Fetched {len(items)} entries for uid={uid}")
            return items

        print(f"Bili API failed for uid={uid}, attempt={attempt}: {data}")
        time.sleep(8 + random.random() * 5)

    return []


def video_id(item):
    return item.get("bvid") or str(item.get("aid"))


def video_link(item):
    bvid = item.get("bvid")
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"

    return f"https://www.bilibili.com/video/av{item.get('aid')}"


def main():
    if TEST_PUSH:
        push("B站提醒测试", "如果你看到这条消息，说明 WxPusher 推送通道正常。")
        return

    seen = load_seen()
    first_run = not bool(seen)
    changed = False

    for up_name, uid in UP_LIST.items():
        old_ids = set(seen.get(uid, []))
        entries = fetch_up_videos(uid)
        time.sleep(6 + random.random() * 4)

        if not entries:
            continue

        new_entries = []
        current_ids = set(old_ids)

        for item in entries:
            item_id = video_id(item)
            if not item_id:
                continue

            if item_id not in old_ids:
                new_entries.append(item)
                current_ids.add(item_id)

        seen[uid] = sorted(current_ids)[-100:]
        changed = True

        if first_run:
            continue

        for item in reversed(new_entries):
            title = item.get("title", "B站新视频")
            link = video_link(item)
            push(
                f"B站更新：{up_name}",
                f'<p><b>{title}</b></p><p><a href="{link}">{link}</a></p>',
            )

    if changed and seen:
        save_seen(seen)
    elif not seen:
        print("No entries fetched, seen.json not updated")


if __name__ == "__main__":
    main()
