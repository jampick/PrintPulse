import time
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.live import Live
from rich.table import Table
from rich import box
from rich.align import Align
from rich.columns import Columns

import io
import sys

# Force UTF-8 output on Windows to handle box-drawing characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True, force_jupyter=False)

BANNER = r"""
 ██████╗ ██████╗ ██╗███╗   ██╗████████╗
 ██╔══██╗██╔══██╗██║████╗  ██║╚══██╔══╝
 ██████╔╝██████╔╝██║██╔██╗ ██║   ██║
 ██╔═══╝ ██╔══██╗██║██║╚██╗██║   ██║
 ██║     ██║  ██║██║██║ ╚████║   ██║
 ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝
 ██████╗ ██╗   ██╗██╗     ███████╗███████╗
 ██╔══██╗██║   ██║██║     ██╔════╝██╔════╝
 ██████╔╝██║   ██║██║     ███████╗█████╗
 ██╔═══╝ ██║   ██║██║     ╚════██║██╔══╝
 ██║     ╚██████╔╝███████╗███████║███████╗
 ╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝"""

MISSION_COMPLETE_ART = r"""
  ███╗   ███╗██╗███████╗███████╗██╗ ██████╗ ███╗   ██╗
  ████╗ ████║██║██╔════╝██╔════╝██║██╔═══██╗████╗  ██║
  ██╔████╔██║██║███████╗███████╗██║██║   ██║██╔██╗ ██║
  ██║╚██╔╝██║██║╚════██║╚════██║██║██║   ██║██║╚██╗██║
  ██║ ╚═╝ ██║██║███████║███████║██║╚██████╔╝██║ ╚████║
  ╚═╝     ╚═╝╚═╝╚══════╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
   ██████╗ ██████╗ ███╗   ███╗██████╗ ██╗     ███████╗████████╗███████╗
  ██╔════╝██╔═══██╗████╗ ████║██╔══██╗██║     ██╔════╝╚══██╔══╝██╔════╝
  ██║     ██║   ██║██╔████╔██║██████╔╝██║     █████╗     ██║   █████╗
  ██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ██║     ██╔══╝     ██║   ██╔══╝
  ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ███████╗███████╗   ██║   ███████╗
   ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝   ╚═╝   ╚══════╝"""

THEMES = {
    "green": {
        "primary": "bright_green",
        "accent": "green",
        "dim": "dim green",
        "border": "bright_green",
        "highlight": "bold bright_white on green",
        "error": "bold bright_red",
    },
    "amber": {
        "primary": "bright_yellow",
        "accent": "yellow",
        "dim": "dim yellow",
        "border": "bright_yellow",
        "highlight": "bold bright_white on dark_orange3",
        "error": "bold bright_red",
    },
}


def get_theme(theme_name: str) -> dict:
    return THEMES.get(theme_name, THEMES["green"])


def show_splash(theme_name: str = "green"):
    theme = get_theme(theme_name)
    banner_text = Text(BANNER, style=theme["primary"])
    tagline = Text(
        "\n>>> PRINTPULSE v0.1 <<<",
        style=theme["highlight"],
        justify="center",
    )
    subtitle = Text(
        "[ Voice. Ink. Paper. ]\n",
        style=theme["dim"],
        justify="center",
    )

    content = Text()
    content.append_text(banner_text)
    content.append("\n")
    content.append_text(tagline)
    content.append("\n")
    content.append_text(subtitle)

    panel = Panel(
        Align.center(content),
        box=box.DOUBLE,
        border_style=theme["border"],
        padding=(1, 2),
    )
    console.print(panel)


def retro_panel(title: str, content, theme_name: str = "green", **kwargs):
    theme = get_theme(theme_name)
    if isinstance(content, str):
        content = Text(content, style=theme["primary"])
    panel = Panel(
        content,
        title=f"[ {title} ]",
        title_align="left",
        box=box.DOUBLE,
        border_style=theme["border"],
        padding=(0, 1),
        **kwargs,
    )
    console.print(panel)


def retro_prompt(choices: list[tuple[str, str]], theme_name: str = "green") -> str:
    """Display a menu and return the selected key.

    choices: list of (key, label) tuples, e.g. [("M", "Microphone"), ("F", "File")]
    """
    theme = get_theme(theme_name)
    lines = []
    for key, label in choices:
        lines.append(f"  [{key}] {label}")
    menu_text = "\n".join(lines)
    retro_panel("SELECT MODE", menu_text, theme_name)

    valid_keys = {k.upper() for k, _ in choices}
    while True:
        console.print(
            Text("\n  >> ", style=theme["primary"]), end=""
        )
        choice = input().strip().upper()
        if choice in valid_keys:
            return choice
        console.print(
            Text("  Invalid selection. Try again.", style=theme["error"])
        )


def retro_menu(title: str, items: list[tuple[str, str]], theme_name: str = "green") -> str:
    """Display a numbered menu and return the selected value.

    items: list of (value, display_label) tuples
    """
    theme = get_theme(theme_name)
    lines = []
    for i, (_, label) in enumerate(items, 1):
        lines.append(f"  [{i:>2}] {label}")
    menu_text = "\n".join(lines)
    retro_panel(title, menu_text, theme_name)

    while True:
        console.print(Text("\n  >> ", style=theme["primary"]), end="")
        choice = input().strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx][0]
        except ValueError:
            # Try matching by name
            for value, label in items:
                if choice.lower() in label.lower() or choice.lower() == value.lower():
                    return value
        console.print(
            Text(f"  Invalid selection. Enter 1-{len(items)}.", style=theme["error"])
        )


def create_progress(theme_name: str = "green") -> Progress:
    theme = get_theme(theme_name)
    return Progress(
        SpinnerColumn("dots", style=theme["primary"]),
        TextColumn("[{task.description}]", style=theme["primary"]),
        BarColumn(
            bar_width=40,
            complete_style=theme["primary"],
            finished_style=theme["accent"],
            style=theme["dim"],
        ),
        TaskProgressColumn(style=theme["primary"]),
        console=console,
    )


@contextmanager
def live_status(message: str, theme_name: str = "green"):
    theme = get_theme(theme_name)
    spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    status_text = Text(f"  {spinner_chars[0]} {message}", style=theme["primary"])
    panel = Panel(
        status_text,
        box=box.SIMPLE,
        border_style=theme["dim"],
        padding=(0, 1),
    )

    with Live(panel, console=console, refresh_per_second=10) as live:
        frame = [0]

        class StatusContext:
            def update(self, new_message: str):
                nonlocal message
                message = new_message

        ctx = StatusContext()

        import threading

        stop_event = threading.Event()

        def animate():
            while not stop_event.is_set():
                frame[0] = (frame[0] + 1) % len(spinner_chars)
                text = Text(
                    f"  {spinner_chars[frame[0]]} {message}",
                    style=theme["primary"],
                )
                live.update(
                    Panel(text, box=box.SIMPLE, border_style=theme["dim"], padding=(0, 1))
                )
                stop_event.wait(0.1)

        t = threading.Thread(target=animate, daemon=True)
        t.start()
        try:
            yield ctx
        finally:
            stop_event.set()
            t.join(timeout=1)


def audio_level_bar(level: float, width: int = 40, theme_name: str = "green") -> Text:
    """Return a Text object showing a VU meter bar for the given level (0.0 to 1.0)."""
    theme = get_theme(theme_name)
    filled = int(level * width)
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    text = Text()
    text.append("  VU [", style=theme["dim"])
    if level > 0.8:
        text.append(bar, style="bold bright_red")
    elif level > 0.5:
        text.append(bar, style=theme["primary"])
    else:
        text.append(bar, style=theme["accent"])
    text.append(f"] {level:.0%}", style=theme["dim"])
    return text


def show_text_result(text: str, theme_name: str = "green"):
    """Display transcribed/entered text in a retro panel."""
    retro_panel("TRANSCRIBED TEXT", text, theme_name)


def error_panel(message: str, theme_name: str = "green"):
    theme = get_theme(theme_name)
    text = Text(f"  ERROR: {message}", style=theme["error"])
    panel = Panel(
        text,
        title="[ ERROR ]",
        title_align="left",
        box=box.DOUBLE,
        border_style="bright_red",
        padding=(0, 1),
    )
    console.print(panel)


def success_message(message: str, theme_name: str = "green"):
    theme = get_theme(theme_name)
    console.print(Text(f"\n  {message}", style=theme["primary"]))


def mission_complete(theme_name: str = "green"):
    theme = get_theme(theme_name)
    art = Text(MISSION_COMPLETE_ART, style=theme["primary"])
    stars = Text(
        "\n  * * * PLOTTING FINISHED SUCCESSFULLY * * *\n",
        style=theme["highlight"],
        justify="center",
    )

    content = Text()
    content.append_text(art)
    content.append("\n")
    content.append_text(stars)

    # Blink effect
    for i in range(4):
        if i % 2 == 0:
            panel = Panel(
                Align.center(content),
                box=box.DOUBLE,
                border_style=theme["border"],
                padding=(1, 2),
            )
        else:
            panel = Panel(
                Align.center(Text("\n" * 8)),
                box=box.DOUBLE,
                border_style=theme["dim"],
                padding=(1, 2),
            )
        console.print(panel, end="\r")
        time.sleep(0.3)

    # Final display
    panel = Panel(
        Align.center(content),
        box=box.DOUBLE,
        border_style=theme["border"],
        padding=(1, 2),
    )
    console.print(panel)


def confirm(prompt_text: str, theme_name: str = "green") -> bool:
    theme = get_theme(theme_name)
    console.print(Text(f"\n  {prompt_text} [Y/n] ", style=theme["primary"]), end="")
    choice = input().strip().lower()
    return choice in ("", "y", "yes")


def scan_line(message: str, theme_name: str = "green", duration: float = 1.0):
    """Display a scanning line animation."""
    theme = get_theme(theme_name)
    width = 50
    steps = int(duration / 0.05)
    with Live(console=console, refresh_per_second=20) as live:
        for i in range(steps):
            pos = i % (width * 2)
            if pos >= width:
                pos = width * 2 - pos - 1
            line = "─" * pos + "█" + "─" * (width - pos - 1)
            text = Text(f"  {message} [{line}]", style=theme["primary"])
            live.update(text)
            time.sleep(0.05)


# ─── ASCII ART ILLUSTRATIONS ───────────────────────────────────────────────
# Fallback art when no story image is available.
# Proper ASCII art — styled for ~70-char-wide retro terminal panels.

STORY_ART = {
    "globe": """
                         ,-------.
                       ,'      _ `.
                      /       )_)  \\
                     :  ______/    :
                     | (__         |
                     :    `)    _  :
                      \\     `--' /
                       `.       ,'
                ~^~^~^~^`-...-'^~^~^~^~
              ~~^~^~^  BREAKING NEWS  ^~^~^~~
                ~^~^~^~^~^~^~^~^~^~^~^~^~
    """,
    "weather": r"""
                    .--.
               .-(    ).
              (___.__)__)
               /  /  /  /
              /  /  /  /      .--.
             /  /  /  /  .-(    ).
                        (___.__)__)
          ~~~  ~~~  ~~~  ~~~  ~~~  ~~~
            T H U N D E R S T O R M
          ~~~  ~~~  ~~~  ~~~  ~~~  ~~~
    """,
    "fire": r"""
                      (
                 (   ) )
                  ) ( (
                 .-----|
                / O   O\
               | \.___/  |    )
                \  `---' /  ( ( )
            ,    `.___.,'    ) )
          (  )  (        )  ( (
           ) (   ) FIRE (    ) )
          (   ) (  ALERT ) (  (
           `-'   `------'   `-'
    """,
    "money": r"""
                .-------.
               /  .---. /|
              /  / $ / / |
             /  '---' /  |
            /  .---. /   |
           /  / $ / /    |
          /  '---' /    /
         /________/    /
         |________|   /
         |   $$   |  /
         | MARKET | /
         |________|/
    """,
    "tech": r"""
          .-----------------------------.
          |  C:\> _                      |
          |                              |
          |  SYSTEM ONLINE               |
          |  > Loading neural net...     |
          |  > AI core initialized       |
          |  > All systems nominal       |
          |                              |
          |  [################] 100%     |
          '-----.-----.-----.-----'------'
                |     |     |     |
          .-----'-----'-----'-----'-----.
          |  [1]  [2]  [3]  [4]  [5]    |
          '-----------------------------'
    """,
    "health": r"""
                    ______
                 .-'      `-.
                /     ++     \
               |    +++++     |
               |   ++++++     |
               |    +++++     |
                \     ++     /
                 `-._____.-'
                   |     |
              _____|     |_____
             |                 |
             |    H E A L T H  |
             |_________________|
    """,
    "sports": r"""
                         ___
                      .-'   `'.
                     /  .===.  \
                    |  / ___ \  |
                    |  ||   ||  |
                     \  '---'  /
                      '-.___.+'
                       /     \
                      /  / \  \
                     /__/   \__\
              .---.               .---.
             / MVP \             / WIN \
             '-----'             '-----'
    """,
    "politics": r"""
                        _
                     .-' '-.
                    /       \
                   |  VOTE   |
                   |  2 0 2 6|
                    \       /
                     '-._.-'
                       |||
                _______|_|_______
               /                 \
              |    ===     ===    |
              |   DEMOCRACY AT    |
              |      W O R K     |
               \_________________/
    """,
    "war": r"""
                         /\
                        /  \
                       / || \
                      /  ||  \
                     /   ||   \
                    / .--||--. \
                     /        \
                    /  ______  \
           ~~~~~~~~/ /      \ \~~~~~~~~
          ~~~~~~~/ /  ALERT   \ \~~~~~~~
         ~~~~~~/  '----..----'  \~~~~~~
          ~~~~~`-------'  `------'~~~~~
    """,
    "science": r"""
                     .  *  .
                   .    /\    .
                  .    /  \    .
                   .  / || \  .
                     / _||_ \
                    | |    | |
                    | |    | |
                    | |    | |
                    | |    | |
                    | '----' |
                    |  ~~~~  |
                    | |    | |
                    '-'    '-'
              === LAB REPORT ===
    """,
    "space": r"""
                  *       .       *
              .       *       .
                   .       .
                     /\
            .       /  \       .
                   / /\ \
          *       / /__\ \       *
                 /________\
                |  ______  |
                | |      | |
               /| |      | |\
              /_|_|______|_|_\
             |________________|
            /  /  /    \  \  \
           *       LAUNCH       *
    """,
    "law": r"""
                    _____
                   / ___ \
                  | |   | |
                  | |___| |
                   \_____/
                  ____|____
                 /    |    \
                /     |     \
               /______|______\
                  |       |
                  |  J    |
                  | U S T |
                  | I C E |
                  |_______|
    """,
    "energy": r"""
                      /\
                     /  \
                    / /\ \
                   / /  \ \
                  / / /\ \ \
                 / / /  \ \ \
                / / /    \ \ \
                \/ /  \/  \ \/
                 \/________\/
                  |   ||   |
                  |   ||   |
                  |___||___|
              === E N E R G Y ===
    """,
    "transport": r"""
                     ____
             ______ ||  ||
            /      \||  ||____
           |  .--.  |-----.__  \
           | |    | |  .--. | __|
           | '----' | |    ||
           |  ____  | '----'|
            \______/|_______|
          ~~(O)~~~~~~~~~~~(O)~~
              TRANSPORT NEWS
    """,
}

# Keyword -> art category mapping
_ART_KEYWORDS = {
    "weather": ["weather", "storm", "rain", "snow", "hurricane", "tornado",
                "flood", "drought", "climate", "temperature", "celsius",
                "forecast", "wind", "heatwave", "cold"],
    "fire": ["fire", "wildfire", "blaze", "burn", "arson", "inferno",
             "explosion", "explode", "blast", "volcano", "eruption"],
    "money": ["economy", "economic", "market", "stock", "trade", "bank",
              "inflation", "recession", "gdp", "financial", "dollar",
              "pound", "euro", "bitcoin", "crypto", "tax", "budget",
              "debt", "profit", "investment", "wall street", "price",
              "cost", "wage", "salary", "billion", "million", "tariff"],
    "tech": ["tech", "technology", "ai", "artificial intelligence", "robot",
             "computer", "software", "app", "cyber", "hack", "data",
             "digital", "internet", "google", "apple", "microsoft",
             "amazon", "meta", "chip", "semiconductor", "startup"],
    "health": ["health", "medical", "hospital", "doctor", "disease", "virus",
               "covid", "vaccine", "cancer", "drug", "nhs", "mental",
               "pandemic", "surgery", "patient", "treatment", "outbreak"],
    "sports": ["sport", "football", "soccer", "basketball", "tennis",
               "cricket", "rugby", "olympic", "championship", "league",
               "match", "game", "player", "coach", "team", "win", "score",
               "cup", "medal", "tournament", "f1", "formula"],
    "politics": ["politic", "election", "vote", "president", "minister",
                 "parliament", "congress", "democrat", "republican",
                 "government", "policy", "campaign", "party", "senate",
                 "legislation", "referendum", "mayor", "governor", "trump",
                 "biden", "starmer", "labour", "conservative", "tory"],
    "war": ["war", "military", "army", "troops", "missile", "bomb",
            "attack", "conflict", "ukraine", "russia", "gaza", "israel",
            "nato", "weapon", "soldier", "combat", "defence", "defense",
            "airstrike", "invasion", "ceasefire", "siege"],
    "science": ["science", "research", "study", "discover", "experiment",
                "dna", "gene", "physics", "chemistry", "biology", "fossil",
                "species", "evolution", "quantum", "molecule", "cell"],
    "space": ["space", "nasa", "rocket", "satellite", "astronaut", "moon",
              "mars", "orbit", "launch", "spacex", "asteroid", "comet",
              "telescope", "galaxy", "star", "planet"],
    "law": ["court", "judge", "trial", "sentence", "prison", "jail",
            "crime", "murder", "arrest", "police", "fbi", "lawsuit",
            "verdict", "guilty", "innocent", "supreme court", "legal"],
    "energy": ["energy", "oil", "gas", "solar", "nuclear", "renewable",
               "power", "electricity", "fossil fuel", "wind farm",
               "pipeline", "opec", "carbon", "emission"],
    "transport": ["transport", "train", "flight", "airline", "airport",
                  "car", "vehicle", "road", "traffic", "ship", "rail",
                  "bus", "strike", "delay", "crash"],
}


def _match_art_category(headline: str) -> str:
    """Match a headline to an ASCII art category by keyword frequency."""
    headline_lower = headline.lower()
    scores = {}
    for category, keywords in _ART_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in headline_lower)
        if score > 0:
            scores[category] = score
    if scores:
        return max(scores, key=scores.get)
    return "globe"  # default


def show_story_art(headline: str, theme_name: str = "green", feed_entry=None):
    """Display ASCII art for a story.

    Priority:
        1. Actual story image converted to ASCII (from RSS feed)
        2. Category-matched fallback art
    """
    theme = get_theme(theme_name)
    category = _match_art_category(headline)
    image_ascii = None

    # Try to render the actual story image as edge-detected ASCII art
    if feed_entry is not None:
        try:
            from printpulse.ascii_art import render_story_ascii
            image_ascii = render_story_ascii(feed_entry, width=60, height=25)
        except Exception:
            pass  # fall through to category art

    if image_ascii:
        art_text = Text(image_ascii, style=theme["primary"])
        max_line = max((len(line) for line in image_ascii.splitlines()), default=0)
        label = Text(f"\n  [{category.upper()}]", style=theme["dim"])
        panel_width = max(max_line + 6, 52)
    else:
        art = STORY_ART.get(category, STORY_ART["globe"])
        art_text = Text(art.rstrip(), style=theme["primary"])
        max_line = max((len(line) for line in art.splitlines()), default=0)
        label = Text(f"\n  [{category.upper()}]", style=theme["dim"])
        panel_width = max(max_line + 6, 52)

    content = Text()
    content.append_text(art_text)
    content.append_text(label)

    panel = Panel(
        content,
        title="[ STORY ART ]",
        title_align="left",
        box=box.DOUBLE,
        border_style=theme["border"],
        padding=(0, 1),
        width=panel_width,
    )
    console.print(panel)
