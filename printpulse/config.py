from dataclasses import dataclass, field


FONT_MAP = {
    "Cursive": "scripts",
    "Block": "futural",
    "Typewriter": "rowmant",
    "Typewriter Light": "rowmand",
    "Times": "timesr",
    "Times Bold": "timesrb",
    "Times Italic": "timesi",
    "Times Italic Bold": "timesib",
    "Gothic": "gothiceng",
    "Gothic Bold": "gothgbt",
    "Italic": "futuram",
    "Roman": "rowmans",
    "Script Bold": "scriptc",
    "Greek": "greek",
    "Cyrillic": "cyrilc",
    "Japanese": "japanese",
    "Markers": "markers",
    "Meteorology": "meteorology",
    "Music": "music",
    "Symbolic": "symbolic",
    "Astrology": "astrology",
    "Math": "mathlow",
}

PAGE_PRESETS = {
    "letter": (8.5, 11.0),
    "a4": (8.27, 11.69),
    "a3": (11.69, 16.54),
}


@dataclass
class Config:
    # Page dimensions (inches)
    page_width_in: float = 8.5
    page_height_in: float = 11.0
    margin_in: float = 0.75
    margin_top_in: float = 0.5

    # Font settings
    font_name: str = "futural"
    font_size: float = 14.0
    line_spacing: float = 1.6

    # Whisper settings
    whisper_model: str = "base"

    # AxiDraw pen settings
    pen_down_speed: int = 25
    pen_up_speed: int = 75
    pen_pos_up: int = 60
    pen_pos_down: int = 40

    # UI
    color_theme: str = "green"

    # Behavior
    dry_run: bool = False
    preview: bool = True
    landscape: bool = True  # AxiDraw oriented landscape; rotate text for portrait reading

    # Output
    output_path: str = ""

    @property
    def page_width_pt(self) -> float:
        return self.page_width_in * 72

    @property
    def page_height_pt(self) -> float:
        return self.page_height_in * 72

    @property
    def margin_pt(self) -> float:
        return self.margin_in * 72

    @property
    def margin_top_pt(self) -> float:
        return self.margin_top_in * 72

    @property
    def text_area_width_pt(self) -> float:
        return self.page_width_pt - 2 * self.margin_pt

    @property
    def text_area_height_pt(self) -> float:
        return self.page_height_pt - self.margin_top_pt - self.margin_pt

    def apply_page_preset(self, preset: str):
        if preset in PAGE_PRESETS:
            self.page_width_in, self.page_height_in = PAGE_PRESETS[preset]
