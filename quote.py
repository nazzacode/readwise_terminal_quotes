#!/usr/bin/env python3
import json, os, random, shutil, subprocess, sys, textwrap, time, urllib.request
from pathlib import Path

TOKEN      = os.getenv('READWISE_TOKEN', '')
CACHE_FILE = Path.home() / '.cache' / 'readwise_quotes.json'
COUNT_TTL  = 86400  # 1 day

RESET  = "\033[0m"
ITALIC = "" if os.environ.get('TMUX') else "\033[3m"
DIM    = "\033[2m"
CYAN   = "\033[36m"

def get(url):
    req = urllib.request.Request(url, headers={'Authorization': f'Token {TOKEN}'})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {'count': 1000, 'count_at': 0, 'queue': []}

def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))

BLUE = "\033[34m"
GREY = "\033[90m"
BOLD = "\033[1m"

def stat_strip(ind, width):
    """Faded system footer: host ▸ os ▸ wm ▸ uptime ▸ mem, from fastfetch json."""
    try:
        r = {m["type"]: m.get("result") for m in json.loads(subprocess.run(
            ["fastfetch", "--format", "json", "-s", "title:os:uptime:memory"],
            capture_output=True, text=True, timeout=2).stdout)}
        up  = r["Uptime"]["uptime"] // 60000
        gb  = lambda b: f"{b / 2**30:.1f}"
        wm  = os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")[0]
        parts = [r["Title"]["hostName"], f"NixOS {r['OS']['versionID']}", wm,
                 f"up {up // 1440}d {up // 60 % 24}h",
                 f"{gb(r['Memory']['used'])}/{gb(r['Memory']['total'])} GB"]
    except Exception:
        return []
    return [f"{ind}{GREY}{'╌' * width}{RESET}",
            f"{ind}{GREY}{' ▸ '.join(x for x in parts if x)}{RESET}"]

def fmt(q):
    """Quote-first: hanging “…”, upright text, — author, title; faded stat footer."""
    term_w = shutil.get_terminal_size(fallback=(80, 24)).columns
    ind    = " " * (5 if term_w >= 74 else 2)
    wrap_w = max(20, min(term_w - 2 * len(ind), 64))
    text   = q["text"].strip().replace(chr(173), "")
    link   = f"{GREY}\033]8;;{q['url']}\033\\↗\033]8;;\033\\{RESET}" if q.get("url") else ""
    lines  = textwrap.fill(f"{text}”", width=wrap_w).split("\n")
    out = [""] + [f"{ind[:-1]}{BLUE}“{RESET}{l}" if i == 0 else f"{ind}{l}"  # “ hangs in the margin
                  for i, l in enumerate(lines)]
    out[-1] = out[-1][:-1] + f"{BLUE}”{RESET}"
    out += ["", f"{ind}{GREY}—{RESET} {q['author']}{GREY}, {ITALIC}{q['title']}{RESET}  {link}", ""]
    out += stat_strip(ind, wrap_w) + [""]
    return "\n".join(out)

def fetch_one(cache):
    if time.time() - cache['count_at'] > COUNT_TTL:
        cache['count'] = get('https://readwise.io/api/v2/highlights/?page_size=1')['count']
        cache['count_at'] = time.time()
    for _ in range(3):
        data = get(f'https://readwise.io/api/v2/highlights/?page_size=1&page={random.randint(1, cache["count"])}')
        if data['results']:
            h = data['results'][0]
            b = get(f'https://readwise.io/api/v2/books/{h["book_id"]}/')
            return {'text': h['text'], 'author': b['author'], 'title': b['title'],
                    'tags': [t['name'] for t in h.get('tags', [])],
                    'url': h.get('readwise_url', '')}

def bg_fetch():
    cache = load_cache()
    try:
        q = fetch_one(cache)
        if q:
            cache['queue'].append(q)
            save_cache(cache)
    except Exception:
        pass

def main():
    if '--fetch' in sys.argv:
        bg_fetch()
        return

    if not TOKEN:
        print("⚠ READWISE_TOKEN not set")
        return

    cache = load_cache()

    if cache['queue']:
        q = cache['queue'].pop(0)  # consume front
        save_cache(cache)
        print(fmt(q))
    else:
        # queue empty — fetch live (first run or lagging behind)
        try:
            q = fetch_one(cache)
            save_cache(cache)
            print(fmt(q) if q else "📚 No highlight found")
        except Exception:
            print("❌ Network error — no cached quotes")
            return

    # always pre-fetch next in background
    subprocess.Popen(
        [sys.executable, __file__, '--fetch'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

if __name__ == '__main__':
    main()
