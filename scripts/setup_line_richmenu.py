#!/usr/bin/env python3
"""LINEリッチメニュー（手動ingestボタン）を作成し、本人にのみリンクする。

ホスト（arigato-nas）で1回実行する運用スクリプト。.envからトークンを読む。
デフォルトのリッチメニューには設定しないので、友人購読者には表示されない。

Usage:
    python3 scripts/setup_line_richmenu.py           # 作成 + 本人にリンク
    python3 scripts/setup_line_richmenu.py --remove  # 削除 + リンク解除
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

RICH_MENU_NAME = "manual-ingest"
API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"

WIDTH, HEIGHT = 800, 270
BG = (10, 14, 26)
ACCENT = (0, 229, 255)
SUB = (140, 150, 170)


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


def find_font(bold: bool):
    from PIL import ImageFont

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

    # 枠線 + 四隅のアクセント（サイバー風）
    draw.rectangle([8, 8, WIDTH - 9, HEIGHT - 9], outline=(30, 40, 60), width=2)
    for x, y, dx, dy in [(8, 8, 1, 1), (WIDTH - 9, 8, -1, 1),
                         (8, HEIGHT - 9, 1, -1), (WIDTH - 9, HEIGHT - 9, -1, -1)]:
        draw.line([x, y, x + 30 * dx, y], fill=ACCENT, width=4)
        draw.line([x, y, x, y + 30 * dy], fill=ACCENT, width=4)

    title_font = ImageFont.truetype(find_font(bold=True), 64, index=0)
    sub_font = ImageFont.truetype(find_font(bold=False), 28, index=0)

    title = "▶ RUN INGEST"
    tw = draw.textlength(title, font=title_font)
    draw.text(((WIDTH - tw) / 2, 62), title, font=title_font, fill=ACCENT)

    sub = "全ソース取り込み・スコア再計算"
    sw = draw.textlength(sub, font=sub_font)
    draw.text(((WIDTH - sw) / 2, 165), sub, font=sub_font, fill=SUB)

    img.save(path, "PNG")


def remove_existing(token: str, owner_id: str) -> None:
    menus = request("GET", f"{API}/richmenu/list", token).get("richmenus", [])
    for menu in menus:
        if menu.get("name") == RICH_MENU_NAME:
            request("DELETE", f"{API}/richmenu/{menu['richMenuId']}", token)
            print(f"deleted: {menu['richMenuId']}")


def main() -> None:
    env = load_env()
    token = env.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    owner_id = env.get("LINE_OWNER_USER_ID", "")
    if not token or not owner_id:
        sys.exit("LINE_CHANNEL_ACCESS_TOKEN / LINE_OWNER_USER_ID が.envにありません")

    if "--remove" in sys.argv:
        request("DELETE", f"{API}/user/{owner_id}/richmenu", token)
        remove_existing(token, owner_id)
        print("removed")
        return

    remove_existing(token, owner_id)

    menu = {
        "size": {"width": WIDTH, "height": HEIGHT},
        "selected": True,
        "name": RICH_MENU_NAME,
        "chatBarText": "メニュー",
        "areas": [{
            "bounds": {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
            "action": {
                "type": "postback",
                "data": "ingest:run",
                "displayText": "ingest実行",
            },
        }],
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
