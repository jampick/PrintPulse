"""Stationery profiles for letter mode.

A StationeryProfile defines the visual style of a letter: header, fonts,
ornament style, and illustration settings. Profiles are stored as JSON
in ~/.printpulse/stationery/ and loaded by name.
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional

from printpulse import ui

# ─── Paths ────────────────────────────────────────────────────────────────────

STATIONERY_DIR = os.path.join(os.path.expanduser("~"), ".printpulse", "stationery")
BUNDLED_DIR = os.path.join(os.path.dirname(__file__), "stationery")


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class HeaderConfig:
    prefix: str = "FROM THE DESK OF"
    name: str = "James Pickard"
    title: str = "Mechanical Explorer & Adventurer"
    font: str = "scripts"
    font_size: float = 20.0
    frame_style: str = "ornamental"


@dataclass
class IllustrationSlot:
    enabled: bool = True
    max_height_in: float = 2.5
    position: str = "top"          # "top" for hero, "inline_right" for supporting


@dataclass
class IllustrationConfig:
    hero: IllustrationSlot = field(default_factory=lambda: IllustrationSlot(
        enabled=True, max_height_in=2.5, position="top"))
    supporting: IllustrationSlot = field(default_factory=lambda: IllustrationSlot(
        enabled=True, max_height_in=1.5, position="inline_right"))


@dataclass
class StationeryProfile:
    name: str = "victorian"
    header: HeaderConfig = field(default_factory=HeaderConfig)
    corner_ornaments: str = "gears"       # "gears", "flourishes", "simple"
    body_font: str = "scripts"
    body_font_size: float = 12.0
    illustrations: IllustrationConfig = field(default_factory=IllustrationConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "StationeryProfile":
        """Build a StationeryProfile from a parsed JSON dict."""
        profile = cls()
        profile.name = data.get("name", profile.name)
        profile.corner_ornaments = data.get("corner_ornaments", profile.corner_ornaments)
        profile.body_font = data.get("body_font", profile.body_font)
        profile.body_font_size = data.get("body_font_size", profile.body_font_size)

        # Header
        hdr = data.get("header", {})
        profile.header = HeaderConfig(
            prefix=hdr.get("prefix", profile.header.prefix),
            name=hdr.get("name", profile.header.name),
            title=hdr.get("title", profile.header.title),
            font=hdr.get("font", profile.header.font),
            font_size=hdr.get("font_size", profile.header.font_size),
            frame_style=hdr.get("frame_style", profile.header.frame_style),
        )

        # Illustrations
        ill = data.get("illustrations", {})
        hero_data = ill.get("hero", {})
        supp_data = ill.get("supporting", {})
        profile.illustrations = IllustrationConfig(
            hero=IllustrationSlot(
                enabled=hero_data.get("enabled", True),
                max_height_in=hero_data.get("max_height_in", 2.5),
                position=hero_data.get("position", "top"),
            ),
            supporting=IllustrationSlot(
                enabled=supp_data.get("enabled", True),
                max_height_in=supp_data.get("max_height_in", 1.5),
                position=supp_data.get("position", "inline_right"),
            ),
        )
        return profile

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict."""
        return {
            "name": self.name,
            "header": {
                "prefix": self.header.prefix,
                "name": self.header.name,
                "title": self.header.title,
                "font": self.header.font,
                "font_size": self.header.font_size,
                "frame_style": self.header.frame_style,
            },
            "corner_ornaments": self.corner_ornaments,
            "body_font": self.body_font,
            "body_font_size": self.body_font_size,
            "illustrations": {
                "hero": {
                    "enabled": self.illustrations.hero.enabled,
                    "max_height_in": self.illustrations.hero.max_height_in,
                    "position": self.illustrations.hero.position,
                },
                "supporting": {
                    "enabled": self.illustrations.supporting.enabled,
                    "max_height_in": self.illustrations.supporting.max_height_in,
                    "position": self.illustrations.supporting.position,
                },
            },
        }


# ─── Loader / Manager ────────────────────────────────────────────────────────

def _ensure_user_dir():
    """Create user stationery dir and seed with bundled profiles if empty."""
    os.makedirs(STATIONERY_DIR, exist_ok=True)
    # Copy bundled profiles that don't already exist in user dir
    if os.path.isdir(BUNDLED_DIR):
        for fname in os.listdir(BUNDLED_DIR):
            if fname.endswith(".json"):
                dest = os.path.join(STATIONERY_DIR, fname)
                if not os.path.isfile(dest):
                    shutil.copy2(os.path.join(BUNDLED_DIR, fname), dest)


def load_profile(name: str) -> StationeryProfile:
    """Load a stationery profile by name.

    Search order:
        1. ~/.printpulse/stationery/{name}.json
        2. Bundled printpulse/stationery/{name}.json
        3. Default (built-in StationeryProfile defaults)
    """
    _ensure_user_dir()

    # User dir
    user_path = os.path.join(STATIONERY_DIR, f"{name}.json")
    if os.path.isfile(user_path):
        with open(user_path, "r", encoding="utf-8") as f:
            return StationeryProfile.from_dict(json.load(f))

    # Bundled
    bundled_path = os.path.join(BUNDLED_DIR, f"{name}.json")
    if os.path.isfile(bundled_path):
        with open(bundled_path, "r", encoding="utf-8") as f:
            return StationeryProfile.from_dict(json.load(f))

    # Fallback to defaults
    ui.success_message(f"Profile '{name}' not found. Using defaults.")
    return StationeryProfile(name=name)


def list_profiles() -> list[str]:
    """Return names of available stationery profiles."""
    _ensure_user_dir()
    names = set()
    for d in (STATIONERY_DIR, BUNDLED_DIR):
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if fname.endswith(".json"):
                    names.add(fname[:-5])
    return sorted(names)


def save_profile(profile: StationeryProfile):
    """Save a profile to the user stationery directory."""
    _ensure_user_dir()
    path = os.path.join(STATIONERY_DIR, f"{profile.name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
