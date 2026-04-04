"""Audio output destinations for typewriter-style feedback.

Provides bell (880 Hz on newline) and keystroke click (20 ms noise burst
on printable characters) sound generators. Both use in-memory numpy arrays
played via sounddevice, with graceful degradation when PortAudio is absent.
"""

from collections.abc import Callable


def make_bell_output() -> Callable[[str], None]:
    """Create an output function that plays a bell sound on newline characters.

    The bell tone is generated in-memory (880 Hz sine wave, 150ms, exponential
    decay). sounddevice and numpy are lazy-imported so the module degrades
    gracefully when PortAudio is unavailable.

    Returns:
        A callable accepting a single character. Plays the bell on '\\n',
        does nothing for other characters. Returns a no-op callable if
        sounddevice or numpy cannot be imported.
    """
    try:
        import numpy as np
        import sounddevice as sd

        sr = 44100
        duration = 0.15
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        bell = (np.sin(2 * np.pi * 880 * t) * np.exp(-20 * t)).astype(np.float32)

        def _bell_write(char: str) -> None:
            if char == "\n":
                try:
                    sd.play(bell, samplerate=sr)
                except OSError:
                    pass

        return _bell_write

    except (ImportError, OSError):

        def _noop(char: str) -> None:
            pass

        return _noop


def make_keystroke_output() -> Callable[[str], None]:
    """Create an output function that plays a typewriter click on each character.

    Generates a short (~20 ms) click sound in-memory: white noise burst mixed
    with a low 200 Hz thump, rapid exponential decay, normalized to 0.5
    amplitude.  The click array is pre-generated once at factory time.

    The returned callable plays the click for every character **except** ``"\\n"``
    and ``"\\r"`` (newlines get the bell sound instead).

    Returns:
        A callable accepting a single character.  Returns a no-op callable if
        sounddevice or numpy cannot be imported.
    """
    try:
        import numpy as np
        import sounddevice as sd

        sr = 44100
        duration = 0.020  # 20 ms click
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        rng = np.random.default_rng(42)  # deterministic noise
        noise = rng.normal(0, 0.3, len(t)).astype(np.float32)
        thump = (np.sin(2 * np.pi * 200 * t) * np.exp(-t * 150)).astype(np.float32)
        click = ((noise + thump) * np.exp(-t * 200)).astype(np.float32)
        click = click / np.max(np.abs(click)) * 0.5

        def _click_write(char: str) -> None:
            if char not in ("\n", "\r"):
                try:
                    sd.play(click, samplerate=sr)
                except OSError:
                    pass

        return _click_write

    except (ImportError, OSError):

        def _noop(char: str) -> None:  # noqa: F811
            pass

        return _noop
