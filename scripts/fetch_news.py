import os, re, sys, time, hashlib, html
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
import pytz
import feedparser
from jinja2 import Environment, FileSystemLoader, select_autoescape


TIMEZONE = "Asia/Iran"
SITE_TITLE = "The Null Pointer"
SITE_DESC = "Automated feed of technology and cybersecurity news — updated daily"
SITE_URL = ""

# RSS feeds (tech + security)
FEEDS = [
    # Tech
    "https://www.theverge.com/rss/index.xml",
    "http://feeds.arstechnica.com/arstechnica/index",
    "https://www.techradar.com/rss",
    "https://www.engadget.com/rss.xml",
    "https://feeds.feedburner.com/Techcrunch",
    "https://www.wired.com/feed/rss",
    "https://www.tomshardware.com/feeds/all",
    # Security
    "https://krebsonsecurity.com/feed/",
    "https://www.bleepingcomputer.com/feed/",
    "https://www.darkreading.com/rss.xml",
    "https://threatpost.com/feed/",
    "https://feeds.feedburner.com/Securityweek",
    "https://feeds.feedburner.com/TheHackersNews",
]

MAX_ITEMS_PER_DAY = 100
RECENT_HOURS = 36
DOCS_DIR = "docs"


def safe_text(s):
    if not s:
        return ""
    s = html.escape(str(s), quote=False)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_dt(dt_val):
    if not dt_val:
        return None
    try:
        if isinstance(dt_val, str):
            dt = dateparser.parse(dt_val)
        else:
            try:
                dt = datetime.fromtimestamp(time.mktime(dt_val))
            except Exception:
                dt = dateparser.parse(str(dt_val))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(pytz.timezone(TIMEZONE))
    except Exception:
        return None


def hash_link(link):
    return hashlib.sha1((link or "").encode("utf-8")).hexdigest()


# Fetch
def collect_items():
    items = []
    now_local = datetime.now(pytz.timezone(TIMEZONE))
    cutoff = now_local - timedelta(hours=RECENT_HOURS)

    for url in FEEDS:
        try:
            fp = feedparser.parse(url)
        except Exception as e:
            print(f"[warn] failed feed: {url} -> {e}", file=sys.stderr)
            continue

        for e in fp.entries:
            link = getattr(e, "link", "") or ""
            title = getattr(e, "title", "") or ""
            summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            published = getattr(e, "published", None) or getattr(e, "updated", None)
            published_parsed = getattr(e, "published_parsed", None) or getattr(
                e, "updated_parsed", None
            )

            dt = normalize_dt(published) or normalize_dt(published_parsed) or now_local

            if dt < cutoff:
                continue

            items.append(
                {
                    "id": hash_link(link),
                    "title": safe_text(title),
                    "summary": safe_text(re.sub("<.*?>", "", summary))[:400],
                    "link": link,
                    "source": safe_text(getattr(fp.feed, "title", "") or ""),
                    "published": dt,
                }
            )

    # De-duplicate by link
    uniq = {}
    for it in items:
        uniq[it["link"]] = it
    items = list(uniq.values())

    # Sort newest first
    items.sort(key=lambda x: x["published"], reverse=True)

    return items[:MAX_ITEMS_PER_DAY]


# Build
def build_site(items):
    os.makedirs(DOCS_DIR, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    now_local = datetime.now(pytz.timezone(TIMEZONE))
    day_slug = now_local.strftime("%Y-%m-%d")
    day_title = now_local.strftime("%Y/%m/%d")

    # Day page
    day_tpl = env.get_template("day.html")
    day_html = day_tpl.render(
        site_title=SITE_TITLE,
        site_desc=SITE_DESC,
        site_url=SITE_URL,
        day_slug=day_slug,
        day_title=day_title,
        items=items,
    )
    with open(os.path.join(DOCS_DIR, f"{day_slug}.html"), "w", encoding="utf-8") as f:
        f.write(day_html)

    # Index/archive
    pages = []
    for name in os.listdir(DOCS_DIR):
        if re.match(r"\d{4}-\d{2}-\d{2}\.html$", name):
            pages.append(name[:-5])
    pages = sorted(pages, reverse=True)

    index_tpl = env.get_template("index.html")
    index_html = index_tpl.render(
        site_title=SITE_TITLE, site_desc=SITE_DESC, pages=pages
    )
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # Optional CNAME (empty placeholder)
    cname_path = os.path.join(DOCS_DIR, "CNAME")
    if not os.path.exists(cname_path):
        with open(cname_path, "w", encoding="utf-8") as f:
            f.write("")


def main():
    items = collect_items()
    build_site(items)
    print(f"Built with {len(items)} items.")


if __name__ == "__main__":
    main()
