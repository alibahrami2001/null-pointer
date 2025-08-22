import os, re, sys, time, hashlib, html
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
import pytz
import feedparser
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape


TIMEZONE = "Asia/Tehran"  # Fixed timezone name
SITE_TITLE = "The Null Pointer"
SITE_DESC = "Automated feed of technology and cybersecurity news — updated daily"
SITE_URL = ""

# Updated RSS feeds with working URLs
FEEDS = [
    # Tech
    "https://www.theverge.com/rss/index.xml",
    "http://feeds.arstechnica.com/arstechnica/index",
    "https://www.techradar.com/rss",
    "https://www.engadget.com/rss.xml",
    "https://techcrunch.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://www.tomshardware.com/feeds/all",
    "https://9to5mac.com/feed/",
    # Security
    "https://krebsonsecurity.com/feed/",
    "https://www.bleepingcomputer.com/feed/",
    "https://www.darkreading.com/rss_simple.asp",
    "https://www.securityweek.com/feed/",
    "https://thehackernews.com/feeds/posts/default",
    "https://www.schneier.com/feed/atom/",
]

MAX_ITEMS_PER_DAY = 80
RECENT_HOURS = 48
DOCS_DIR = "docs"


def safe_text(s):
    """Clean and escape text content"""
    if not s:
        return ""
    s = html.escape(str(s), quote=False)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_dt(dt_val):
    """Normalize datetime to local timezone"""
    if not dt_val:
        return None
    try:
        if isinstance(dt_val, str):
            dt = dateparser.parse(dt_val)
        else:
            try:
                dt = datetime.fromtimestamp(time.mktime(dt_val))
            except (TypeError, ValueError, OverflowError):
                dt = dateparser.parse(str(dt_val))
        
        if not dt:
            return None
            
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        
        local_tz = pytz.timezone(TIMEZONE)
        return dt.astimezone(local_tz)
    except Exception as e:
        print(f"[warn] datetime parse error: {e}", file=sys.stderr)
        return None


def hash_link(link):
    """Generate unique hash for deduplication"""
    return hashlib.sha1((link or "").encode("utf-8")).hexdigest()


def fetch_feed_with_retry(url, max_retries=3):
    """Fetch RSS feed with retry logic"""
    for attempt in range(max_retries):
        try:
            # Set user agent to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0; +https://github.com)'
            }
            
            # Try with requests first for better error handling
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                return feedparser.parse(response.content)
            except Exception:
                # Fallback to direct feedparser
                return feedparser.parse(url)
                
        except Exception as e:
            print(f"[warn] attempt {attempt + 1} failed for {url}: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
    
    print(f"[error] all attempts failed for {url}", file=sys.stderr)
    return None


def collect_items():
    """Collect and process news items from all feeds"""
    items = []
    local_tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(local_tz)
    cutoff = now_local - timedelta(hours=RECENT_HOURS)

    print(f"Collecting items from {len(FEEDS)} feeds...")
    print(f"Cutoff time: {cutoff}")

    for i, url in enumerate(FEEDS, 1):
        print(f"Processing feed {i}/{len(FEEDS)}: {url}")
        
        fp = fetch_feed_with_retry(url)
        if not fp or not hasattr(fp, 'entries'):
            continue

        feed_items = 0
        for entry in fp.entries:
            try:
                link = getattr(entry, "link", "") or ""
                title = getattr(entry, "title", "") or ""
                
                if not link or not title:
                    continue

                summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                published = getattr(entry, "published", None) or getattr(entry, "updated", None)
                published_parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)

                # Try to get publication date
                dt = normalize_dt(published) or normalize_dt(published_parsed)
                if not dt:
                    dt = now_local  # Use current time if no date available

                # Skip old items
                if dt < cutoff:
                    continue

                # Clean summary
                clean_summary = re.sub(r"<.*?>", "", summary)
                clean_summary = re.sub(r"\s+", " ", clean_summary).strip()
                if len(clean_summary) > 300:
                    clean_summary = clean_summary[:300] + "..."

                items.append({
                    "id": hash_link(link),
                    "title": safe_text(title),
                    "summary": safe_text(clean_summary),
                    "link": link,
                    "source": safe_text(getattr(fp.feed, "title", "") or "Unknown"),
                    "published": dt,
                })
                feed_items += 1

            except Exception as e:
                print(f"[warn] error processing entry: {e}", file=sys.stderr)
                continue

        print(f"  → Found {feed_items} recent items")

    print(f"Total items collected: {len(items)}")

    # Remove duplicates by link
    unique_items = {}
    for item in items:
        if item["link"] not in unique_items:
            unique_items[item["link"]] = item

    items = list(unique_items.values())
    print(f"After deduplication: {len(items)} items")

    # Sort by publication date (newest first)
    items.sort(key=lambda x: x["published"], reverse=True)

    # Limit items
    items = items[:MAX_ITEMS_PER_DAY]
    print(f"Final item count: {len(items)}")

    return items


def build_site(items):
    """Build the static site"""
    print("Building site...")
    
    os.makedirs(DOCS_DIR, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    local_tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(local_tz)
    day_slug = now_local.strftime("%Y-%m-%d")
    day_title = now_local.strftime("%B %d, %Y")

    print(f"Building page for {day_slug}")

    # Build daily page
    day_template = env.get_template("day.html")
    day_html = day_template.render(
        site_title=SITE_TITLE,
        site_desc=SITE_DESC,
        site_url=SITE_URL,
        day_slug=day_slug,
        day_title=day_title,
        items=items,
    )
    
    day_file = os.path.join(DOCS_DIR, f"{day_slug}.html")
    with open(day_file, "w", encoding="utf-8") as f:
        f.write(day_html)
    print(f"Created {day_file}")

    # Build archive index
    pages = []
    for filename in os.listdir(DOCS_DIR):
        if re.match(r"\d{4}-\d{2}-\d{2}\.html$", filename):
            pages.append(filename[:-5])  # Remove .html extension
    
    pages = sorted(pages, reverse=True)  # Newest first
    print(f"Found {len(pages)} daily pages for archive")

    index_template = env.get_template("index.html")
    index_html = index_template.render(
        site_title=SITE_TITLE,
        site_desc=SITE_DESC,
        pages=pages
    )
    
    index_file = os.path.join(DOCS_DIR, "index.html")
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"Updated {index_file}")

    # Create empty CNAME file for GitHub Pages
    cname_path = os.path.join(DOCS_DIR, "CNAME")
    if not os.path.exists(cname_path):
        with open(cname_path, "w", encoding="utf-8") as f:
            f.write("")  # Empty file - user can add custom domain later

    print("Site build complete!")


def main():
    """Main execution function"""
    try:
        print("Starting news aggregation...")
        items = collect_items()
        
        if not items:
            print("No items found. Creating empty page.")
        
        build_site(items)
        print(f"✅ Successfully built site with {len(items)} items.")
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
