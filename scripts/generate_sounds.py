#!/usr/bin/env python3
"""
Generate simple test sounds for Access IRC
Requires: numpy, scipy
"""

import os
import sys

try:
    import numpy as np
    from scipy.io import wavfile
except ImportError:
    print("Error: numpy and scipy are required to generate sounds")
    print("Install with: pip install numpy scipy")
    sys.exit(1)


def generate_beep(frequency: int, duration: float, filename: str):
    """
    Generate a simple sine wave beep

    Args:
        frequency: Frequency in Hz
        duration: Duration in seconds
        filename: Output filename
    """
    sample_rate = 22050
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Generate sine wave
    wave = np.sin(2 * np.pi * frequency * t)

    # Apply envelope to avoid clicks (fade in/out)
    fade_samples = int(sample_rate * 0.01)  # 10ms fade
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)

    wave[:fade_samples] *= fade_in
    wave[-fade_samples:] *= fade_out

    # Convert to 16-bit PCM
    wave = (wave * 32767 * 0.5).astype(np.int16)  # 50% volume

    wavfile.write(filename, sample_rate, wave)
    print(f"Generated: {filename}")


def generate_two_tone(freq1: int, freq2: int, duration: float, filename: str):
    """
    Generate a distinctive two-tone beep (like a notification chirp)

    Args:
        freq1: First frequency in Hz
        freq2: Second frequency in Hz
        duration: Total duration in seconds
        filename: Output filename
    """
    sample_rate = 22050

    # Split duration between two tones
    tone_duration = duration / 2
    samples_per_tone = int(sample_rate * tone_duration)

    # Generate first tone
    t1 = np.linspace(0, tone_duration, samples_per_tone)
    wave1 = np.sin(2 * np.pi * freq1 * t1)

    # Generate second tone
    t2 = np.linspace(0, tone_duration, samples_per_tone)
    wave2 = np.sin(2 * np.pi * freq2 * t2)

    # Concatenate the two tones
    wave = np.concatenate([wave1, wave2])

    # Apply envelope to avoid clicks
    fade_samples = int(sample_rate * 0.01)  # 10ms fade
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)

    wave[:fade_samples] *= fade_in
    wave[-fade_samples:] *= fade_out

    # Convert to 16-bit PCM
    wave = (wave * 32767 * 0.5).astype(np.int16)  # 50% volume

    wavfile.write(filename, sample_rate, wave)
    print(f"Generated: {filename}")


def generate_three_tone(freq1: int, freq2: int, freq3: int, duration: float, filename: str):
    """
    Generate a three-tone sequence (good for completion sounds)

    Args:
        freq1: First frequency in Hz
        freq2: Second frequency in Hz
        freq3: Third frequency in Hz
        duration: Total duration in seconds
        filename: Output filename
    """
    sample_rate = 22050

    # Split duration between three tones
    tone_duration = duration / 3
    samples_per_tone = int(sample_rate * tone_duration)

    # Generate tones
    t = np.linspace(0, tone_duration, samples_per_tone)
    wave1 = np.sin(2 * np.pi * freq1 * t)
    wave2 = np.sin(2 * np.pi * freq2 * t)
    wave3 = np.sin(2 * np.pi * freq3 * t)

    # Concatenate the tones
    wave = np.concatenate([wave1, wave2, wave3])

    # Apply envelope to avoid clicks
    fade_samples = int(sample_rate * 0.01)  # 10ms fade
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)

    wave[:fade_samples] *= fade_in
    wave[-fade_samples:] *= fade_out

    # Convert to 16-bit PCM
    wave = (wave * 32767 * 0.5).astype(np.int16)  # 50% volume

    wavfile.write(filename, sample_rate, wave)
    print(f"Generated: {filename}")


def main():
    """Generate all sound files"""

    # Determine output directory (package data directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    sounds_dir = os.path.join(project_root, "access_irc", "data", "sounds")

    os.makedirs(sounds_dir, exist_ok=True)

    print(f"Generating test sound files to {sounds_dir}...")

    # Generate different tones for different events
    # Message sounds
    generate_beep(800, 0.2, os.path.join(sounds_dir, "mention.wav"))     # High pitch for mentions
    generate_beep(600, 0.15, os.path.join(sounds_dir, "message.wav"))    # Medium pitch for messages
    generate_two_tone(700, 850, 0.3, os.path.join(sounds_dir, "privmsg.wav"))  # Distinctive two-tone for private messages
    generate_two_tone(650, 800, 0.25, os.path.join(sounds_dir, "notice.wav"))  # Two-tone chirp for notices

    # User activity sounds
    generate_beep(500, 0.1, os.path.join(sounds_dir, "join.wav"))        # Lower pitch for joins
    generate_beep(400, 0.1, os.path.join(sounds_dir, "part.wav"))        # Lower pitch for parts
    generate_two_tone(450, 350, 0.2, os.path.join(sounds_dir, "quit.wav"))  # Descending tone for quits

    # Channel invite sound - attention-grabbing ascending pattern
    generate_three_tone(500, 650, 800, 0.35, os.path.join(sounds_dir, "invite.wav"))

    # DCC transfer completion sounds - pleasant ascending tones
    generate_three_tone(400, 500, 600, 0.3, os.path.join(sounds_dir, "dcc_receive_complete.wav"))  # Ascending for receive
    generate_three_tone(450, 550, 650, 0.3, os.path.join(sounds_dir, "dcc_send_complete.wav"))     # Slightly higher for send

    print(f"\nSound files generated successfully in {sounds_dir}")
    print("You can replace these with your own sound files if desired.")


if __name__ == "__main__":
    main()
