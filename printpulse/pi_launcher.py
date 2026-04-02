"""Systemd entry point for the PrintPulse Pi appliance.

Reads ~/.printpulse_appliance.json and launches watch mode with
the configured feeds, interval, and settings. Called by the
printpulse.service systemd unit.
"""

import sys
import os

# Add project root to path so pi.appliance is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main():
    from pi.appliance import load_config
    from printpulse.app import run

    config = load_config()

    if not config.get("enabled", True):
        print("PrintPulse appliance is disabled in config. Exiting.")
        sys.exit(0)

    feeds = config.get("feeds", [])
    if not feeds:
        print("No RSS feeds configured. Add feeds via the web UI.")
        sys.exit(1)

    # Build the CLI argv that app.run() expects
    argv = []

    # Watch mode with feeds
    argv.append("--watch")
    argv.extend(feeds)

    # Interval
    interval = config.get("interval", 300)
    argv.extend(["--watch-interval", str(interval)])

    # Max prints per cycle
    max_prints = config.get("max_prints", 3)
    argv.extend(["--max-prints", str(max_prints)])

    # Always thermal, always auto-confirm
    argv.extend(["--printer", "thermal"])
    argv.append("-y")

    # Theme
    theme = config.get("theme", "green")
    argv.extend(["--theme", theme])

    # Quiet hours
    if config.get("quiet_enabled", True):
        quiet_start = config.get("quiet_start", "22:00")
        quiet_end = config.get("quiet_end", "08:00")
        argv.extend(["--quiet-start", quiet_start, "--quiet-end", quiet_end])
        wake_mode = config.get("quiet_wake_mode", "latest")
        argv.extend(["--quiet-wake-mode", wake_mode])

    print(f"PrintPulse appliance starting: {len(feeds)} feed(s), "
          f"interval={interval}s, max_prints={max_prints}")
    print(f"Feeds: {', '.join(feeds)}")

    run(argv)


if __name__ == "__main__":
    main()
