import json
import os
from pathlib import Path

import feedparser
import requests


WXPUSHER_SPT = os.environ["WXPUSHER_SPT"]

# 改成你要关注的 UP 主 UID
UP_LIST = {
    "影视飓风": "946974",
    # "另一个UP": "123456",
}

STATE_FILE = Path("seen.json")


def load_seen():
    if not STATE_FILE.exists():
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
    url = f"https://rsshub.app/bilibili/user/video/{uid}"
    feed = feedparser.parse(url)

    if getattr(feed, "bozo", False):
        raise RuntimeError(f"RSS parse failed: {url}")

    return feed.entries


def main():
    seen = load_seen()
    first_run = not STATE_FILE.exists()
    changed = False

    for up_name, uid in UP_LIST.items():
        old_ids = set(seen.get(uid, []))
        entries = fetch_up_videos(uid)

        new_entries = []
        current_ids = set(old_ids)

        for entry in entries:
            item_id = getattr(entry, "id", None) or entry.link
            if item_id not in old_ids:
                new_entries.append(entry)
                current_ids.add(item_id)

        seen[uid] = list(current_ids)[-100:]

        # 首次运行只记录历史视频，不推送，避免刷屏
        if first_run:
            changed = True
            continue

        for entry in reversed(new_entries):
            title = f"B站更新：{up_name}"
            content = f'''
            <p><b>{entry.title}</b></p>
            <p><a href="{entry.link}">{entry.link}</a></p>
            '''
            push(title, content)

        if new_entries:
            changed = True

    if changed or first_run:
        save_seen(seen)


if __name__ == "__main__":
    main()
