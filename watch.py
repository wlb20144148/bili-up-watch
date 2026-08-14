import json
import os
from pathlib import Path

import requests


WXPUSHER_SPT = os.environ["WXPUSHER_SPT"]

UP_LIST = {
    "影视飓风": "946974",
    "IC一站式服务": "3461580865931962",
    "智视界AI时代": "499440615",
    "泫九AI": "21384754",
    # "另一个UP": "123456",
}

STATE_FILE = Path("seen.json")


def load_seen():
    if not STATE_FILE.exists():
        return {}

    if STATE_FILE.stat().st_size == 0:
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


def fetch_up_videos(uid):
    url = "https://app.biliapi.com/x/v2/space/archive/cursor"
    params = {
        "vmid": uid,
        "order": "pubdate",
        "ps": 20,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://space.bilibili.com/{uid}",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()

    data = resp.json()
    if data.get("code") != 0:
        print(f"Bili API failed for uid={uid}: {data}")
        return []

    items = data.get("data", {}).get("item", [])
    print(f"Fetched {len(items)} entries for uid={uid}")
    return items


def video_id(item):
    return item.get("bvid") or str(item.get("param"))


def video_link(item):
    bvid = item.get("bvid")
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"

    aid = item.get("param")
    return f"https://www.bilibili.com/video/av{aid}"


def main():
    seen = load_seen()
    first_run = not STATE_FILE.exists()
    changed = False

    for up_name, uid in UP_LIST.items():
        old_ids = set(seen.get(uid, []))
        entries = fetch_up_videos(uid)

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

        seen[uid] = list(current_ids)[-100:]

        if first_run:
            changed = True
            continue

        for item in reversed(new_entries):
            title = item.get("title", "B站新视频")
            link = video_link(item)

            push(
                f"B站更新：{up_name}",
                f'<p><b>{title}</b></p><p><a href="{link}">{link}</a></p>',
            )

        if new_entries:
            changed = True

    if seen:
        save_seen(seen)
    else:
        print("No entries fetched, seen.json not updated")


if __name__ == "__main__":
    main()
