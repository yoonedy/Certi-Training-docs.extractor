"""주간 식단표 이미지 → 요일별 메뉴 텍스트 (Tesseract OCR, 한국어).

FOODONE 'ABB코리아 주간식단표' 양식을 기준으로
  - 초록 줄 = 날짜 머리줄, 노란 줄 = 사이드, 그 위 = 중식, 그 아래 = 석식
  - 머리줄의 밝은 틈 = 요일 칸 경계
을 색으로 찾아 칸마다 따로 글자를 읽는다. 읽은 글자는 메뉴 사전(tools/menu_words.txt +
data/menu/menu_words.txt)과 자모 단위로 비교해 가장 가까운 메뉴로 고친다.

    python menu_ocr.py 식단표.png     → 결과를 콘솔에 출력 (점검용)
"""
import datetime as dt
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
WORD_FILES = [ROOT / "tools" / "menu_words.txt", ROOT / "data" / "menu" / "menu_words.txt"]
GREEN, YELLOW = (146, 208, 80), (255, 192, 0)
WEEK = "월화수목금"


def _near(c, t, d=45):
    return sum(abs(a - b) for a, b in zip(c, t)) < d


def load_words():
    words = []
    for f in WORD_FILES:
        if f.is_file():
            words += [l.strip() for l in f.read_text(encoding="utf-8-sig").splitlines() if l.strip() and not l.startswith("#")]
    return words


# ---------------------------------------------------------------- 표 칸 찾기

def _is_green(c):  # 색조로 판단 — JPG로 저장돼 색이 조금 틀어져도 됨
    r, g, b = c[:3]
    return g >= 140 and g - r >= 35 and g - b >= 70


def _is_yellow(c):  # 진한 노랑만 (아래쪽 연노랑 안내 상자는 제외)
    r, g, b = c[:3]
    return r >= 200 and g >= 130 and b <= 110 and r - g >= 15


def _band(im, test, y_from=0, need=2, min_rows=1):
    """여러 지점(가로 25·45·65·85%) 중 need곳 이상이 test를 만족하는 첫 가로 띠 → (y0, y1).
    띠 안의 글자 때문에 몇 줄 끊겨도 한 띠로 보고, min_rows보다 얇은 띠(경계선 번짐)는 건너뜀"""
    w, h = im.size
    xs = [int(w * f) for f in (0.25, 0.45, 0.65, 0.85)]
    rows = [y for y in range(y_from, h) if sum(test(im.getpixel((x, y))) for x in xs) >= need]
    gap = max(3, h // 100)
    i = 0
    while i < len(rows):
        y0 = y1 = rows[i]
        i += 1
        while i < len(rows) and rows[i] - y1 <= gap:
            y1 = rows[i]
            i += 1
        if y1 - y0 + 1 >= min_rows:
            return y0, y1
    return None


def _is_note(c):  # 아래쪽 연노랑 안내 상자 (원산지·알레르기)
    r, g, b = c[:3]
    return r >= 235 and g >= 225 and b <= 215 and r - b >= 30


def bottom_of_table(im, y_from):
    """석식 칸이 끝나는 y: 연노랑 안내 상자가 있으면 그 위, 없으면 그림 끝"""
    band = _band(im, _is_note, y_from, need=3, min_rows=max(3, im.height // 120))
    return (band[0] - 1) if band else im.height - 2


def find_grid(im):
    """→ (머리줄 y0,y1), (사이드 y0,y1), [칸 경계 x...]  (첫 칸 = 중식/석식 이름 칸)"""
    w, h = im.size
    head = _band(im, _is_green)
    if not head:
        raise ValueError("날짜 머리줄(초록)을 찾지 못함")
    hy0, hy1 = head
    side = _band(im, _is_yellow, hy1 + 1)
    if not side:
        raise ValueError("사이드 줄(노랑)을 찾지 못함")
    sy0, sy1 = side
    # 요일 칸 경계: 머리줄 중 글자가 가장 적은 줄에서 초록이 끊기는 밝은 틈
    y = max(range(hy0, hy1 + 1), key=lambda yy: sum(_is_green(im.getpixel((x, yy))) for x in range(0, w, 3)))
    gaps = [x for x in range(w) if min(im.getpixel((x, y))[:3]) > 150 and not _is_green(im.getpixel((x, y)))]
    runs = []
    for x in gaps:
        if runs and x - runs[-1][-1] <= 1:
            runs[-1].append(x)
        else:
            runs.append([x])
    cuts = [r[len(r) // 2] for r in runs]
    # 그림 가장자리에 여백이 없으면 바깥 경계가 그림 끝과 겹쳐 안 보임 → 빠진 쪽 끝을 채움
    if len(cuts) == 6:
        if cuts[0] > w * 0.02:
            cuts = [0] + cuts
        elif cuts[-1] < w * 0.98:
            cuts = cuts + [w - 1]
    if len(cuts) < 7:
        raise ValueError(f"요일 칸 경계를 {len(cuts)}개만 찾음")
    cuts = cuts[:7]
    widths = [b - a for a, b in zip(cuts[1:6], cuts[2:7])]  # 다섯 요일 칸은 너비가 비슷해야 식단표
    if min(widths) < max(widths) * 0.7:
        raise ValueError(f"요일 칸 너비가 고르지 않음 {widths}")
    return (hy0, hy1), (sy0, sy1), cuts


# ---------------------------------------------------------------- 글자 읽기

def _tesseract(img, psm, cmd):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cell.png"
        img.save(p)
        # 작은 칸 하나라 스레드 1개가 훨씬 빠름 (여러 스레드면 서로 CPU를 뺏어 수십 배 느려짐)
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        out = subprocess.run([cmd, str(p), "-", "-l", "kor", "--psm", str(psm)],
                             capture_output=True, text=True, encoding="utf-8", timeout=60, env=env).stdout
    lines = [re.sub(r"[^가-힣a-zA-Z0-9/&]", "", l) for l in out.splitlines()]
    return [l for l in lines if len(l) >= 2]


def _cell(im, box, scale):
    c = im.crop(box)
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    # 빨강 채널: 노란 바탕은 하얗게, 회색 바탕·검은 글자는 그대로 → 노란 칸도 잘 읽힘
    return ImageOps.expand(ImageOps.autocontrast(c.split()[0]), 20, fill=255)


def _jamo(s):
    return unicodedata.normalize("NFD", s)


def correct(word, words, cutoff):
    """→ (고친 단어, 일치도). 사전에 가까운 메뉴가 없으면 읽은 그대로"""
    if word in words:
        return word, 1.0
    jw = _jamo(word)
    best, score = word, 0.0
    for v in words:
        r = difflib.SequenceMatcher(None, jw, _jamo(v)).ratio()
        if r > score:
            best, score = v, r
    return (best, score) if score >= cutoff else (word, score)


def _read_list(im, box, psm, cmd, words, cutoff, split_slash=False):
    """두 배율로 읽어서 사전과 더 잘 맞는 쪽을 고름"""
    best, best_score = [], -1.0
    for scale in (3, 4):
        lines = _tesseract(_cell(im, box, scale), psm, cmd)
        if split_slash:
            lines = [p for p in "".join(lines).split("/") if p]
        fixed = [correct(l, words, cutoff) for l in lines]
        score = sum(s for _, s in fixed) / len(fixed) if fixed else 0
        if score > best_score:
            best, best_score = [f for f, _ in fixed], score
    return best


def _week_start(im, head, cuts, cmd, today):
    """머리줄 날짜(예: 10월26일)로 그 주 월요일을 찾음. 못 읽으면 이번 주 월요일"""
    votes = {}
    for k, (x0, x1) in enumerate(zip(cuts[1:6], cuts[2:7])):
        text = "".join(_tesseract(_cell(im, (x0 + 2, head[0], x1 - 1, head[1] + 1), 4), 7, cmd))
        m = re.search(r"(\d{1,2})월(\d{1,2})일", text)
        if not m:
            continue
        try:
            d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        if (d - today).days > 180:  # 연말·연초 경계
            d = d.replace(year=d.year - 1)
        mon = d - dt.timedelta(days=k)
        if mon.weekday() == 0:
            votes[mon] = votes.get(mon, 0) + 1
    if votes:
        return max(votes, key=votes.get)
    return None  # 못 읽으면 '이번 주'로 추측하지 않음 (지난 식단표를 이번 주로 보여주지 않게)


def read_menu(path, cmd="tesseract", cutoff=0.68, today=None):
    today = today or dt.date.today()
    if not shutil.which(cmd) and not Path(cmd).is_file():
        raise FileNotFoundError(f"Tesseract 실행 파일 없음: {cmd}")
    im = Image.open(path).convert("RGB")
    head, side, cuts = find_grid(im)
    words = set(load_words())
    monday = _week_start(im, head, cuts, cmd, today)
    bottom = bottom_of_table(im, side[1] + 1)
    days = []
    for k, (x0, x1) in enumerate(zip(cuts[1:6], cuts[2:7])):
        date = monday + dt.timedelta(days=k) if monday else None
        days.append({
            "date": date.isoformat() if date else None,
            "label": f"{date.month}월 {date.day}일 ({WEEK[k]})" if date else f"{WEEK[k]}요일",
            "lunch": _read_list(im, (x0 + 2, head[1] + 1, x1 - 1, side[0]), 6, cmd, words, cutoff),
            "side": _read_list(im, (x0 + 2, side[0], x1 - 1, side[1] + 1), 7, cmd, words, cutoff, split_slash=True),
            "dinner": _read_list(im, (x0 + 2, side[1] + 1, x1 - 1, bottom), 6, cmd, words, cutoff),
        })
    return {"week_start": monday.isoformat() if monday else None, "days": days}


if __name__ == "__main__":
    import json
    print(json.dumps(read_menu(sys.argv[1]), ensure_ascii=False, indent=1))
