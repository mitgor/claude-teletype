"""Bell sound output destination for typewriter-style audio feedback.

Generates an in-memory 880 Hz tone with exponential decay and plays it
on each newline character, creating a typewriter bell effect.
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
                sd.play(bell, samplerate=sr)

        return _bell_write

    except (ImportError, OSError):

        def _noop(char: str) -> None:
            pass

        return _noop
