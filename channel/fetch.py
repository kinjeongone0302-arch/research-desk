"""텔레그램 채널 아카이브 수집.

~/report-bot 의 Telethon 개인계정 세션을 그대로 쓴다(이미 로그인돼 있다).
이미지는 받아서 docs/media/ 에 두고, 게시물은 JSON 으로 남긴다.
증분 수집 — 이미 받은 메시지 id 는 건너뛴다.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RB = Path.home() / "report-bot"
sys.path.insert(0, str(RB))
from dotenv import load_dotenv
load_dotenv(RB / ".env")
from telethon import TelegramClient

BASE = Path(__file__).resolve().parent
STORE = BASE / "posts.json"
MEDIA = BASE.parent / "docs" / "media"

CHANNEL = "태린이아빠"          # 대화 목록에서 이름으로 찾는다
DAYS = 90


def load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except json.JSONDecodeError:
            pass
    return {"channel": None, "posts": {}}


async def run(days=DAYS, channel=CHANNEL):
    db = load()
    have = set(db["posts"])
    MEDIA.mkdir(parents=True, exist_ok=True)

    c = TelegramClient(str(RB / "user_session"),
                       int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    await c.connect()
    if not await c.is_user_authorized():
        raise SystemExit("텔레그램 세션 만료 — ~/report-bot/login_telethon.py 를 직접 실행해 재로그인")

    target = None
    async for d in c.iter_dialogs():
        if channel in (d.name or ""):
            target = d
            break
    if not target:
        raise SystemExit(f"채널을 찾지 못했다: {channel}")
    db["channel"] = target.name
    print(f"채널: {target.name}", flush=True)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    new = 0
    async for m in c.iter_messages(target.entity, offset_date=None):
        if m.date < since:
            break
        key = str(m.id)
        if key in have:
            continue
        text = (m.message or "").strip()
        img = None
        if m.photo:
            f = MEDIA / f"{m.id}.jpg"
            if not f.exists():
                try:
                    await c.download_media(m, file=str(f))
                except Exception:
                    f = None
            img = f.name if f and f.exists() else None
        if not text and not img:
            continue
        db["posts"][key] = {
            "id": m.id,
            "t": m.date.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
            "text": text,
            "img": img,
            "views": getattr(m, "views", None),
            "group": getattr(m, "grouped_id", None) and str(m.grouped_id),
        }
        new += 1
        if new % 200 == 0:
            # 중간 저장. 텔레그램이 미디어 내려받기에 속도 제한을 걸어 오래 걸리는데,
            # 끝에 한 번만 저장하면 중간에 끊길 때 통째로 날아간다.
            STORE.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")))
            print(f"  {new}건 수집", flush=True)

    STORE.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")))
    print(f"신규 {new}건 · 누적 {len(db['posts'])}건 · 이미지 {len(list(MEDIA.glob('*.jpg')))}장", flush=True)
    await c.disconnect()


if __name__ == "__main__":
    asyncio.run(run(int(sys.argv[1]) if len(sys.argv) > 1 else DAYS))
