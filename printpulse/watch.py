import json
import logging
import os
import time
from datetime import datetime

from printpulse import ui
from printpulse.secure_fs import secure_write_json

logger = logging.getLogger("printpulse.watch")

SEEN_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_seen.json")


def _load_seen() -> dict:
    """Load seen state: {"ids": [...], "titles": [...]}"""
    if os.path.isfile(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Migrate from old format (plain list of IDs)
            if isinstance(data, list):
                return {"ids": set(data), "titles": set()}
            return {"ids": set(data.get("ids", [])), "titles": set(data.get("titles", []))}
    return {"ids": set(), "titles": set()}


def _save_seen(seen: dict):
    secure_write_json(
        SEEN_FILE,
        {"ids": list(seen["ids"]), "titles": list(seen["titles"])},
        indent=0,
    )


def fetch_new_items(feed_url: str, max_items: int = 3) -> list[dict]:
    """Fetch new (unseen) items from a single RSS/Atom feed.

    Returns list of dicts with 'id', 'title', 'summary', '_entry', '_source' keys.
    """
    from printpulse import require_dependency
    feedparser = require_dependency("feedparser")

    seen = _load_seen()
    feed = feedparser.parse(feed_url)

    # Extract feed source name
    feed_title = feed.feed.get("title", "")
    if not feed_title:
        from urllib.parse import urlparse
        feed_title = urlparse(feed_url).netloc

    # Only consider the top N slots in the feed — don't reach deeper
    candidates = feed.entries if max_items <= 0 else feed.entries[:max_items]

    new_items = []
    for entry in candidates:
        entry_id = getattr(entry, "id", None) or getattr(entry, "link", entry.title)
        title = entry.get("title", "No title")
        # Skip if we've seen this ID or this exact title before
        if entry_id in seen["ids"] or title in seen["titles"]:
            continue
        new_items.append({
            "id": entry_id,
            "title": title,
            "summary": entry.get("summary", ""),
            "_entry": entry,  # raw feedparser entry for image extraction
            "_source": feed_title,
        })

    return new_items


def fetch_new_items_multi(feed_urls: list[str], max_items: int = 3) -> list[dict]:
    """Fetch new items from multiple feeds. max_items applies per feed."""
    all_items = []
    for url in feed_urls:
        try:
            items = fetch_new_items(url, max_items)
            all_items.extend(items)
        except Exception as e:
            logger.error("Feed fetch failed for %s: %s", url, e)
            ui.error_panel("Feed error: could not fetch feed.", "green")
    return all_items


def mark_seen(items: list[dict]):
    """Mark items as seen so they won't be plotted again."""
    seen = _load_seen()
    for item in items:
        seen["ids"].add(item["id"])
        seen["titles"].add(item["title"])
    _save_seen(seen)


def _is_in_quiet_hours(quiet_start: str, quiet_end: str) -> bool:
    """Check if current time falls within quiet hours.

    Handles midnight crossover (e.g. 22:00–08:00).
    """
    now = datetime.now().time()
    start_h, start_m = int(quiet_start[:2]), int(quiet_start[3:5])
    end_h, end_m = int(quiet_end[:2]), int(quiet_end[3:5])

    from datetime import time as dtime
    start = dtime(start_h, start_m)
    end = dtime(end_h, end_m)

    if start <= end:
        # Same-day range (e.g. 08:00–17:00)
        return start <= now < end
    else:
        # Crosses midnight (e.g. 22:00–08:00)
        return now >= start or now < end


def run_watch_loop(feed_urls: list[str], interval: int, max_prints: int,
                   plot_callback, theme: str = "green",
                   quiet_start: str | None = None,
                   quiet_end: str | None = None):
    """Main watch loop. Polls feeds and calls plot_callback(text) for each new item."""
    from rich.live import Live
    from rich.text import Text as RText

    feed_list = "\n".join(f"  {url}" for url in feed_urls)
    quiet_label = f"Quiet hours: {quiet_start}–{quiet_end}" if quiet_start and quiet_end else "Quiet hours: off"
    ui.retro_panel(
        "WATCH MODE",
        f"Feeds ({len(feed_urls)}):\n{feed_list}\n"
        f"Poll interval: {interval}s  |  Max per feed: {max_prints or 'unlimited'}\n"
        f"{quiet_label}",
        theme,
    )
    use_quiet = bool(quiet_start and quiet_end)

    # First run: seed seen file, but leave the top N unseen so we
    # immediately print the current top story on first poll
    if not os.path.isfile(SEEN_FILE):
        from printpulse import require_dependency
        feedparser = require_dependency("feedparser")
        seen = {"ids": set(), "titles": set()}
        skip = max_prints if max_prints > 0 else 1
        for feed_url in feed_urls:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[skip:]:
                    entry_id = getattr(entry, "id", None) or getattr(entry, "link", entry.title)
                    title = entry.get("title", "")
                    seen["ids"].add(entry_id)
                    if title:
                        seen["titles"].add(title)
            except Exception as e:
                logger.warning("Error seeding seen items for %s: %s", feed_url, e)
        _save_seen(seen)
        ui.success_message(
            f"First run: top {skip} story(ies) per feed will print now. "
            f"{len(seen['ids'])} older items marked as seen.",
            theme,
        )

    t = ui.get_theme(theme)
    poll_count = 0

    try:
        # Single Live context — one line that never scrolls while idle
        with Live(console=ui.console, refresh_per_second=2, transient=True) as live:
            while True:
                # ── POLL ──
                poll_count += 1
                now = datetime.now().strftime("%I:%M:%S %p")
                live.update(RText(
                    f"  [{now}] Polling {len(feed_urls)} feed(s)... (check #{poll_count})",
                    style=t["primary"],
                ))

                try:
                    items = fetch_new_items_multi(feed_urls, max_prints)
                except Exception as e:
                    logger.error("Feed poll failed: %s", e)
                    live.update(RText(
                        f"  [{now}] Feed error — check logs for details",
                        style=t["error"],
                    ))
                    # Wait then retry
                    for remaining in range(interval, 0, -1):
                        bar_w = 40
                        filled = int((interval - remaining) / interval * bar_w)
                        bar = "=" * filled + ">" + " " * (bar_w - filled - 1)
                        live.update(RText(
                            f"  [{now}] Error — retry in {remaining}s [{bar}]",
                            style=t["error"],
                        ))
                        time.sleep(1)
                    continue

                if not items:
                    # ── IDLE: countdown on the SAME line ──
                    for remaining in range(interval, 0, -1):
                        bar_w = 40
                        filled = int((interval - remaining) / interval * bar_w)
                        bar = "=" * filled + ">" + " " * (bar_w - filled - 1)
                        live.update(RText(
                            f"  Last: {now} | No new items | "
                            f"Check #{poll_count} | Next in {remaining}s [{bar}]",
                            style=t["primary"],
                        ))
                        time.sleep(1)
                else:
                    # ── NEW ITEMS: break out of Live to print story panels ──
                    live.update(RText(
                        f"  [{now}] Found {len(items)} new item(s)!",
                        style=t["primary"],
                    ))

                # Stop Live temporarily to print story content normally
                if items:
                    # Check quiet hours — skip printing but don't mark as seen
                    if use_quiet and _is_in_quiet_hours(quiet_start, quiet_end):
                        live.update(RText(
                            f"  [{now}] {len(items)} new item(s) queued — quiet hours ({quiet_start}–{quiet_end})",
                            style=t["primary"],
                        ))
                        logger.info("Quiet hours active (%s–%s): %d item(s) deferred",
                                    quiet_start, quiet_end, len(items))
                        items = []  # Clear so we skip the print block below

                if items:
                    live.stop()

                    ui.retro_panel("NEW ITEMS", f"Found {len(items)} new item(s).", theme)
                    for i, item in enumerate(items, 1):
                        title = item["title"]
                        source = item.get("_source", "")
                        label = f"ITEM {i}/{len(items)}"
                        if source:
                            label += f" ({source})"
                        ui.retro_panel(label, title, theme)
                        ui.show_story_art(title, theme, feed_entry=item.get("_entry"))
                        try:
                            plot_callback(title, feed_item=item)
                            mark_seen([item])
                        except Exception as e:
                            logger.error("Plot/print error: %s", e)
                            ui.error_panel("Plot error — check logs for details.", theme)

                    # Resume Live for the next idle countdown
                    live.start()

    except KeyboardInterrupt:
        ui.success_message("\nWatch mode stopped.", theme)
