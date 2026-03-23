import os
import queue
import threading

from printpulse import ui
from printpulse.secure_fs import secure_tempfile, secure_delete

_whisper_model = None
_whisper_model_name = None


def _get_whisper_model(model_name: str, theme_name: str = "green"):
    global _whisper_model, _whisper_model_name
    if _whisper_model is not None and _whisper_model_name == model_name:
        return _whisper_model

    import whisper

    with ui.live_status(
        f"Loading Whisper model '{model_name}' (first run downloads it)...",
        theme_name,
    ):
        _whisper_model = whisper.load_model(model_name)
        _whisper_model_name = model_name
    return _whisper_model


def record_audio(
    duration: float | None = None,
    sample_rate: int = 16000,
    theme_name: str = "green",
) -> str:
    """Record audio from the default microphone.

    If duration is None, records until the user presses Enter.
    Returns the path to a temporary WAV file.
    """
    import sounddevice as sd
    import soundfile as sf

    tmp_path = secure_tempfile(suffix=".wav")

    if duration is not None:
        # Fixed-duration recording
        ui.retro_panel(
            "RECORDING",
            f"Recording for {duration:.1f} seconds...",
            theme_name,
        )
        audio_data = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        # Show progress while recording
        with ui.create_progress(theme_name) as progress:
            task = progress.add_task("Recording", total=int(duration * 10))
            for _ in range(int(duration * 10)):
                import time
                time.sleep(0.1)
                progress.advance(task)
        sd.wait()
        sf.write(tmp_path, audio_data, sample_rate, subtype="PCM_16")
    else:
        # Open-ended recording with live VU meter
        ui.retro_panel(
            "RECORDING",
            "Press ENTER to stop recording...",
            theme_name,
        )

        audio_queue = queue.Queue()
        stop_event = threading.Event()

        def audio_callback(indata, frames, time_info, status):
            audio_queue.put(indata.copy())

        with sf.SoundFile(
            tmp_path, mode="w", samplerate=sample_rate, channels=1, subtype="PCM_16"
        ) as sfile:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                callback=audio_callback,
                blocksize=1024,
            ):
                from rich.live import Live
                from rich.panel import Panel
                from rich import box

                level_text = ui.audio_level_bar(0.0, theme_name=theme_name)
                with Live(
                    Panel(level_text, box=box.SIMPLE, border_style=ui.get_theme(theme_name)["dim"]),
                    console=ui.console,
                    refresh_per_second=15,
                ) as live:
                    # Start a thread to wait for Enter
                    def wait_for_enter():
                        input()
                        stop_event.set()

                    enter_thread = threading.Thread(target=wait_for_enter, daemon=True)
                    enter_thread.start()

                    while not stop_event.is_set():
                        try:
                            chunk = audio_queue.get(timeout=0.05)
                            sfile.write(chunk)
                            # Compute RMS level
                            import numpy as np
                            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
                            level = min(rms * 5, 1.0)  # Scale for visibility
                            level_text = ui.audio_level_bar(level, theme_name=theme_name)
                            live.update(
                                Panel(
                                    level_text,
                                    box=box.SIMPLE,
                                    border_style=ui.get_theme(theme_name)["dim"],
                                )
                            )
                        except queue.Empty:
                            pass

    ui.success_message("Recording saved.", theme_name)
    return tmp_path


def _load_audio_as_float32(audio_path: str):
    """Load audio file as float32 numpy array at 16kHz mono, using soundfile.

    This avoids requiring ffmpeg, which Whisper normally uses via its
    own load_audio() function.
    """
    import soundfile as sf

    import numpy as np

    data, sr = sf.read(audio_path, dtype="float32")

    # Convert stereo to mono if needed
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample to 16kHz if needed (Whisper expects 16000 Hz)
    if sr != 16000:
        from scipy.signal import resample

        num_samples = int(len(data) * 16000 / sr)
        data = resample(data, num_samples).astype(np.float32)

    return data


def transcribe(audio_path: str, model_name: str = "base", theme_name: str = "green") -> str:
    """Transcribe an audio file using Whisper."""
    import whisper

    model = _get_whisper_model(model_name, theme_name)

    with ui.live_status("Transcribing audio with Whisper...", theme_name):
        # Load audio ourselves to avoid ffmpeg dependency
        audio = _load_audio_as_float32(audio_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(model.device)
        options = whisper.DecodingOptions(language="en", fp16=False)
        result = whisper.decode(model, mel, options)

    text = result.text.strip()
    return text


def load_audio_file(path: str) -> str:
    """Validate and return the path to an audio file."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    supported = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}
    if ext not in supported:
        raise ValueError(f"Unsupported audio format '{ext}'. Supported: {', '.join(sorted(supported))}")

    return path
