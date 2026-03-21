import threading

from printpulse.config import Config
from printpulse import ui


def check_plotter_connection() -> bool:
    """Check if an AxiDraw plotter is connected."""
    try:
        from pyaxidraw import axidraw
    except ImportError:
        return False

    try:
        ad = axidraw.AxiDraw()
        ad.interactive()
        connected = ad.connect()
        if connected:
            ad.disconnect()
        return connected
    except Exception:
        return False


def plot_svg(svg_path: str, config: Config) -> bool:
    """Send an SVG file to the AxiDraw plotter.

    Returns True on success, False on failure.
    """
    if config.dry_run:
        ui.retro_panel(
            "DRY RUN",
            f"Would plot: {svg_path}\n  (Skipping hardware — dry run mode)",
            config.color_theme,
        )
        return True

    try:
        from pyaxidraw import axidraw
    except ImportError:
        ui.error_panel(
            "pyaxidraw is not installed.\n"
            "  Install from: https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip\n"
            "  Or use --dry-run to test without hardware.",
            config.color_theme,
        )
        return False

    error_holder = [None]

    def do_plot():
        try:
            ad = axidraw.AxiDraw()
            ad.plot_setup(svg_path)
            ad.options.speed_pendown = config.pen_down_speed
            ad.options.speed_penup = config.pen_up_speed
            ad.options.pen_pos_up = config.pen_pos_up
            ad.options.pen_pos_down = config.pen_pos_down
            ad.options.reordering = 2  # Full path reordering
            ad.plot_run()
        except Exception as e:
            error_holder[0] = e

    # Run plot in a thread so the UI can show a spinner
    plot_thread = threading.Thread(target=do_plot)
    plot_thread.start()

    with ui.live_status("Plotting in progress... do not disturb the plotter", config.color_theme):
        plot_thread.join()

    if error_holder[0]:
        ui.error_panel(f"Plotting failed: {error_holder[0]}", config.color_theme)
        return False

    return True
