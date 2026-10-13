import json
import logging
import os
import time
from datetime import datetime

from printpulse import ui
from printpulse.secure_fs import secure_write_json

logger = logging.getLogger("printpulse.watch")

SEEN_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_seen.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_history.json")
RETRY_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_retry.json")
QUIET_QUEUE_FILE = os.path.join(os.path.expanduser("~"), ".printpulse_quiet_queue.json")
_MAX_HISTORY = 200  # Keep last N items
_MAX_RETRIES = 3    # Max retry attempts per item


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
            "link": getattr(entry, "link", ""),
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


def load_history() -> list[dict]:
    """Load print history: list of {title, source, timestamp}."""
    if os.path.isfile(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_history(items: list[dict]):
    """Append printed items to history with timestamps."""
    history = load_history()
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    for item in items:
        history.append({
            "title": item["title"],
            "source": item.get("_source", ""),
            "link": item.get("link", ""),
            "timestamp": now_str,
        })
    # Trim to max
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    secure_write_json(HISTORY_FILE, history)


def _load_retry_queue() -> list[dict]:
    """Load retry queue: list of {id, title, summary, _source, attempts}."""
    if os.path.isfile(RETRY_FILE):
        try:
            with open(RETRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_retry_queue(queue: list[dict]):
    """Save retry queue to disk."""
    secure_write_json(RETRY_FILE, queue)


def _add_to_retry(item: dict):
    """Add a failed item to the retry queue."""
    queue = _load_retry_queue()
    # Check if already in queue
    for q_item in queue:
        if q_item.get("id") == item.get("id"):
            q_item["attempts"] = q_item.get("attempts", 0) + 1
            _save_retry_queue(queue)
            return
    queue.append({
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "link": item.get("link", ""),
        "_source": item.get("_source", ""),
        "attempts": 1,
    })
    _save_retry_queue(queue)


def _remove_from_retry(item_id: str):
    """Remove a successfully printed item from the retry queue."""
    queue = _load_retry_queue()
    queue = [q for q in queue if q.get("id") != item_id]
    _save_retry_queue(queue)


def _load_quiet_queue() -> list[dict]:
    """Load quiet-hours queue: list of {id, title, summary, _source}."""
    if os.path.isfile(QUIET_QUEUE_FILE):
        try:
            with open(QUIET_QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_quiet_queue(queue: list[dict]):
    """Save quiet-hours queue to disk."""
    secure_write_json(QUIET_QUEUE_FILE, queue)


def _enqueue_quiet_items(items: list[dict]):
    """Persist items to the quiet queue, skipping duplicates."""
    queue = _load_quiet_queue()
    existing_ids = {q.get("id") for q in queue}
    for item in items:
        if item.get("id") not in existing_ids:
            queue.append({
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "link": item.get("link", ""),
                "_source": item.get("_source", ""),
            })
            existing_ids.add(item.get("id"))
    _save_quiet_queue(queue)


def mark_seen(items: list[dict]):
    """Mark items as seen so they won't be plotted again."""
    seen = _load_seen()
    for item in items:
        seen["ids"].add(item["id"])
        seen["titles"].add(item["title"])
    _save_seen(seen)


def _is_in_quiet_hours(quiet_start: str, quiet_end: str, tz: str | None = None) -> bool:
    """Check if current time falls within quiet hours.

    Handles midnight crossover (e.g. 22:00–08:00).
    If *tz* is an IANA timezone name (e.g. "America/New_York") the check is
    performed in that timezone; otherwise the system local time is used.
    """
    if tz:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(tz)).time()
        except Exception:
            now = datetime.now().time()
    else:
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


def _filter_quiet_queue_latest(queue: list[dict]) -> list[dict]:
    """Keep only the most recent item per source from the quiet queue.

    Items later in the list are considered more recent (appended in arrival order).
    """
    latest_by_source: dict[str, dict] = {}
    for item in queue:
        source = item.get("_source", "")
        latest_by_source[source] = item  # last one wins
    return list(latest_by_source.values())


def run_watch_loop(feed_urls: list[str], interval: int, max_prints: int,
                   plot_callback, theme: str = "green",
                   quiet_start: str | None = None,
                   quiet_end: str | None = None,
                   quiet_tz: str | None = None,
                   quiet_wake_mode: str = "latest"):
    """Main watch loop. Polls feeds and calls plot_callback(text) for each new item."""
    from rich.live import Live
    from rich.text import Text as RText

    feed_list = "\n".join(f"  {url}" for url in feed_urls)
    if quiet_start and quiet_end:
        tz_name = datetime.now().astimezone().strftime("%Z")
        quiet_label = f"Quiet hours: {quiet_start}–{quiet_end} ({tz_name})"
    else:
        quiet_label = "Quiet hours: off"
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

                # ── QUIET QUEUE: flush items saved during quiet hours ──
                quiet_queue = _load_quiet_queue()
                if quiet_queue and not (use_quiet and _is_in_quiet_hours(quiet_start, quiet_end, quiet_tz)):
                    live.stop()
                    if quiet_wake_mode == "latest":
                        _save_quiet_queue([])  # Clear entire queue
                        total_queued = len(quiet_queue)
                        quiet_queue = _filter_quiet_queue_latest(quiet_queue)
                        skipped = total_queued - len(quiet_queue)
                        msg = (f"Quiet hours ended — printing {len(quiet_queue)} latest item(s)"
                               f" ({skipped} older item(s) discarded).")
                    elif quiet_wake_mode == "next":
                        # Print only the oldest item, keep the rest queued
                        quiet_queue, remaining = quiet_queue[:1], quiet_queue[1:]
                        _save_quiet_queue(remaining)
                        msg = (f"Quiet hours ended — printing next item"
                               f" ({len(remaining)} still queued).")
                    else:
                        _save_quiet_queue([])  # Clear entire queue
                        msg = f"Quiet hours ended — printing {len(quiet_queue)} saved item(s)."
                    ui.retro_panel("QUIET QUEUE", msg, theme)
                    for i, q_item in enumerate(quiet_queue, 1):
                        title = q_item["title"]
                        source = q_item.get("_source", "")
                        label = f"QUEUED {i}/{len(quiet_queue)}"
                        if source:
                            label += f" ({source})"
                        ui.retro_panel(label, title, theme)
                        fake_item = {
                            "id": q_item["id"], "title": title,
                            "summary": q_item.get("summary", ""),
                            "link": q_item.get("link", ""),
                            "_source": source,
                        }
                        try:
                            plot_callback(title, feed_item=fake_item)
                            _append_history([fake_item])
                            _remove_from_retry(q_item["id"])
                        except Exception as e:
                            logger.error("Quiet queue print error for '%s': %s", title, e)
                            ui.error_panel("Print error — check logs for details.", theme)
                            _add_to_retry(fake_item)
                    live.start()

                # ── RETRY QUEUE: process failed items first ──
                retry_queue = _load_retry_queue()
                retryable = [r for r in retry_queue if r.get("attempts", 0) < _MAX_RETRIES]
                expired = [r for r in retry_queue if r.get("attempts", 0) >= _MAX_RETRIES]
                if expired:
                    # Remove items that exceeded max retries
                    for r in expired:
                        logger.warning("Retry limit reached for '%s', giving up", r.get("title"))
                        mark_seen([{"id": r["id"], "title": r["title"]}])
                    _save_retry_queue(retryable)

                if retryable and not (use_quiet and _is_in_quiet_hours(quiet_start, quiet_end, quiet_tz)):
                    live.stop()
                    ui.retro_panel("RETRY", f"Retrying {len(retryable)} failed item(s).", theme)
                    for r_item in retryable:
                        title = r_item["title"]
                        ui.retro_panel(
                            f"RETRY ({r_item.get('attempts', 0)}/{_MAX_RETRIES})",
                            title, theme,
                        )
                        fake_item = {
                            "id": r_item["id"], "title": title,
                            "summary": r_item.get("summary", ""),
                            "link": r_item.get("link", ""),
                            "_source": r_item.get("_source", ""),
                        }
                        try:
                            plot_callback(title, feed_item=fake_item)
                            mark_seen([fake_item])
                            _append_history([fake_item])
                            _remove_from_retry(r_item["id"])
                            ui.success_message(f"Retry succeeded: {title}", theme)
                        except Exception as e:
                            logger.error("Retry failed for '%s': %s", title, e)
                            _add_to_retry(fake_item)
                    live.start()

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
                    # Check quiet hours — persist to queue and mark seen so they're not lost
                    if use_quiet and _is_in_quiet_hours(quiet_start, quiet_end, quiet_tz):
                        _enqueue_quiet_items(items)
                        mark_seen(items)
                        total_queued = len(_load_quiet_queue())
                        live.update(RText(
                            f"  [{now}] {len(items)} item(s) saved to quiet queue "
                            f"({total_queued} total) — quiet hours ({quiet_start}–{quiet_end})",
                            style=t["primary"],
                        ))
                        logger.info("Quiet hours active (%s–%s): %d item(s) saved to queue",
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
                            _append_history([item])
                            _remove_from_retry(item.get("id", ""))
                        except Exception as e:
                            logger.error("Plot/print error: %s", e)
                            ui.error_panel("Plot error — check logs for details.", theme)
                            _add_to_retry(item)

                    # Resume Live for the next idle countdown
                    live.start()

    except KeyboardInterrupt:
        ui.success_message("\nWatch mode stopped.", theme)
