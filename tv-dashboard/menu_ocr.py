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

def find_grid(im):
    """→ (머리줄 y0,y1), (사이드 y0,y1), [칸 경계 x...]  (첫 칸 = 중식/석식 이름 칸)"""
    w, h = im.size
    xm = int(w * 0.33)
    head = [y for y in range(h) if _near(im.getpixel((xm, y)), GREEN)]
    if not head:
        raise ValueError("날짜 머리줄(초록)을 찾지 못함")
    hy0, hy1 = head[0], head[-1]
    side = [y for y in range(hy1, h) if _near(im.getpixel((xm, y)), YELLOW)]
    if not side:
        raise ValueError("사이드 줄(노랑)을 찾지 못함")
    sy0, sy1 = side[0], side[-1]
    y = hy0 + 2
    gaps = [x for x in range(w) if min(im.getpixel((x, y))) > 150 and not _near(im.getpixel((x, y)), GREEN, 60)]
    runs = []
    for x in gaps:
        if runs and x - runs[-1][-1] <= 1:
            runs[-1].append(x)
        else:
            runs.append([x])
    cuts = [r[len(r) // 2] for r in runs]
    if len(cuts) < 7:
        raise ValueError(f"요일 칸 경계를 {len(cuts)}개만 찾음")
    return (hy0, hy1), (sy0, sy1), cuts[:7]


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
    return today - dt.timedelta(days=today.weekday())


def read_menu(path, cmd="tesseract", cutoff=0.68, today=None):
    today = today or dt.date.today()
    if not shutil.which(cmd) and not Path(cmd).is_file():
        raise FileNotFoundError(f"Tesseract 실행 파일 없음: {cmd}")
    im = Image.open(path).convert("RGB")
    head, side, cuts = find_grid(im)
    words = set(load_words())
    monday = _week_start(im, head, cuts, cmd, today)
    days = []
    for k, (x0, x1) in enumerate(zip(cuts[1:6], cuts[2:7])):
        date = monday + dt.timedelta(days=k)
        days.append({
            "date": date.isoformat(),
            "label": f"{date.month}월 {date.day}일 ({WEEK[k]})",
            "lunch": _read_list(im, (x0 + 2, head[1] + 1, x1 - 1, side[0]), 6, cmd, words, cutoff),
            "side": _read_list(im, (x0 + 2, side[0], x1 - 1, side[1] + 1), 7, cmd, words, cutoff, split_slash=True),
            "dinner": _read_list(im, (x0 + 2, side[1] + 1, x1 - 1, im.height - 2), 6, cmd, words, cutoff),
        })
    return {"week_start": monday.isoformat(), "days": days}


if __name__ == "__main__":
    import json
    print(json.dumps(read_menu(sys.argv[1]), ensure_ascii=False, indent=1))
