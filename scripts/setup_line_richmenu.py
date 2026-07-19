#!/usr/bin/env python3
"""LINEリッチメニュー（手動トリガー3ボタン）を作成し、本人にのみリンクする。

ボタン: INGEST（全ソース取り込み）/ HEALTH（ソースヘルスレポート）/ MOOD（調子の3択質問）。
ホスト（arigato-nas）で1回実行する運用スクリプト。.envからトークンを読む。
デフォルトのリッチメニューには設定しないので、友人購読者には表示されない。

Usage:
    python3 scripts/setup_line_richmenu.py           # 作成 + 本人にリンク（既存は置き換え）
    python3 scripts/setup_line_richmenu.py --remove  # 削除 + リンク解除
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

RICH_MENU_NAME = "manual-triggers"
API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"

# 横長スリムバー（表示高さ = 画面幅 × 400/2500 = 16%。旧800x270の約半分）
WIDTH, HEIGHT = 2500, 400
BG = (10, 14, 26)
BORDER = (30, 40, 60)
SUB = (140, 150, 170)

BUTTONS = [
    {"title": "▶ INGEST", "sub": "全ソース取り込み", "accent": (0, 229, 255),
     "data": "ingest:run", "display": "ingest実行"},
    {"title": "♥ HEALTH", "sub": "ソース健全性チェック", "accent": (0, 255, 156),
     "data": "menu:health", "display": "ヘルスチェック"},
    {"title": "◎ MOOD", "sub": "今日の調子を記録", "accent": (255, 184, 77),
     "data": "menu:subjective", "display": "調子の記録"},
]


def load_env() -> dict:
    env = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def request(method: str, url: str, token: str, body: bytes | None = None,
            content_type: str = "application/json") -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}",
        **({"Content-Type": content_type} if body else {}),
    })
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def find_font(bold: bool) -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("Noto Sans CJK font not found")


def generate_image(path: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    cell = WIDTH // len(BUTTONS)

    title_font = ImageFont.truetype(find_font(bold=True), 96, index=0)
    sub_font = ImageFont.truetype(find_font(bold=False), 44, index=0)

    draw.rectangle([4, 4, WIDTH - 5, HEIGHT - 5], outline=BORDER, width=2)
    for i, btn in enumerate(BUTTONS):
        x0 = i * cell
        if i > 0:
            draw.line([x0, 30, x0, HEIGHT - 30], fill=BORDER, width=2)

        tw = draw.textlength(btn["title"], font=title_font)
        draw.text((x0 + (cell - tw) / 2, 92), btn["title"],
                  font=title_font, fill=btn["accent"])
        sw = draw.textlength(btn["sub"], font=sub_font)
        draw.text((x0 + (cell - sw) / 2, 240), btn["sub"], font=sub_font, fill=SUB)

        # 各ボタン下部のアクセントライン
        draw.line([x0 + cell * 0.35, HEIGHT - 34, x0 + cell * 0.65, HEIGHT - 34],
                  fill=btn["accent"], width=5)

    img.save(path, "PNG")


def remove_existing(token: str) -> None:
    menus = request("GET", f"{API}/richmenu/list", token).get("richmenus", [])
    for menu in menus:
        if menu.get("name") in (RICH_MENU_NAME, "manual-ingest"):
            request("DELETE", f"{API}/richmenu/{menu['richMenuId']}", token)
            print(f"deleted: {menu['richMenuId']} ({menu.get('name')})")


def main() -> None:
    env = load_env()
    token = env.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    owner_id = env.get("LINE_OWNER_USER_ID", "")
    if not token or not owner_id:
        sys.exit("LINE_CHANNEL_ACCESS_TOKEN / LINE_OWNER_USER_ID が.envにありません")

    if "--remove" in sys.argv:
        request("DELETE", f"{API}/user/{owner_id}/richmenu", token)
        remove_existing(token)
        print("removed")
        return

    remove_existing(token)

    cell = WIDTH // len(BUTTONS)
    menu = {
        "size": {"width": WIDTH, "height": HEIGHT},
        "selected": True,
        "name": RICH_MENU_NAME,
        "chatBarText": "メニュー",
        "areas": [
            {
                "bounds": {"x": i * cell, "y": 0, "width": cell, "height": HEIGHT},
                "action": {
                    "type": "postback",
                    "data": btn["data"],
                    "displayText": btn["display"],
                },
            }
            for i, btn in enumerate(BUTTONS)
        ],
    }
    menu_id = request(
        "POST", f"{API}/richmenu", token, json.dumps(menu).encode()
    )["richMenuId"]
    print(f"created: {menu_id}")

    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        generate_image(f.name)
        request(
            "POST", f"{API_DATA}/richmenu/{menu_id}/content", token,
            Path(f.name).read_bytes(), content_type="image/png",
        )
    print("image uploaded")

    request("POST", f"{API}/user/{owner_id}/richmenu/{menu_id}", token)
    print(f"linked to owner: {owner_id[:8]}...")


if __name__ == "__main__":
    main()
