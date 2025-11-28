#!/usr/bin/env python3
"""
Sound Manager for Access IRC
Handles playing notification sounds using GStreamer
"""

import os
from typing import Dict, Optional
from pathlib import Path

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    GST_AVAILABLE = True
except (ImportError, ValueError) as e:
    GST_AVAILABLE = False
    print(f"Warning: GStreamer not available: {e}")
    print("Sound notifications will be disabled.")


class SoundManager:
    """Manages sound notifications for IRC events using GStreamer"""

    def __init__(self, config_manager):
        """
        Initialize sound manager

        Args:
            config_manager: ConfigManager instance for getting sound paths
        """
        self.config = config_manager
        self.sounds: Dict[str, Optional[str]] = {}  # Store file URIs
        self.players: Dict[str, Optional[Gst.Element]] = {}  # Store playbin elements
        self.initialized = False

        if GST_AVAILABLE and self.config.are_sounds_enabled():
            self._initialize_gstreamer()
            self._load_sounds()

    def _initialize_gstreamer(self) -> None:
        """Initialize GStreamer"""
        try:
            # GStreamer is already initialized via Gst.init(None) at module level
            self.initialized = True
            print("Sound system initialized (GStreamer)")
        except Exception as e:
            print(f"Failed to initialize sound system: {e}")
            self.initialized = False

    def _load_sounds(self) -> None:
        """Load all configured sound files"""
        if not self.initialized:
            return

        sound_types = ["mention", "message", "notice", "join", "part"]

        for sound_type in sound_types:
            sound_path = self.config.get_sound_path(sound_type)
            if sound_path and os.path.exists(sound_path):
                try:
                    # Convert to absolute path and file:// URI
                    abs_path = os.path.abspath(sound_path)
                    uri = Path(abs_path).as_uri()

                    # Create a playbin for this sound
                    player = Gst.ElementFactory.make("playbin", f"{sound_type}_player")
                    if player:
                        player.set_property("uri", uri)

                        # Set up bus signal watch once per player
                        bus = player.get_bus()
                        bus.add_signal_watch()

                        def on_message(bus, message, player):
                            if message.type == Gst.MessageType.EOS:
                                # End of stream - stop playback
                                player.set_state(Gst.State.NULL)
                            elif message.type == Gst.MessageType.ERROR:
                                # Error occurred
                                err, debug = message.parse_error()
                                print(f"GStreamer error: {err}")
                                player.set_state(Gst.State.NULL)

                        bus.connect("message", on_message, player)

                        self.sounds[sound_type] = uri
                        self.players[sound_type] = player
                        print(f"Loaded {sound_type} sound: {sound_path}")
                    else:
                        print(f"Failed to create player for {sound_type}")
                        self.sounds[sound_type] = None
                        self.players[sound_type] = None
                except Exception as e:
                    print(f"Failed to load {sound_type} sound from {sound_path}: {e}")
                    self.sounds[sound_type] = None
                    self.players[sound_type] = None
            else:
                self.sounds[sound_type] = None
                self.players[sound_type] = None
                if sound_path:
                    print(f"Sound file not found: {sound_path}")

    def play(self, sound_type: str) -> None:
        """
        Play a sound notification

        Args:
            sound_type: Type of sound to play (mention, message, notice, join, part)
        """
        if not self.initialized or not self.config.are_sounds_enabled():
            return

        player = self.players.get(sound_type)
        if player:
            try:
                # Stop any currently playing instance and reset to start
                player.set_state(Gst.State.NULL)
                # Start playing (bus callback will handle cleanup)
                player.set_state(Gst.State.PLAYING)
            except Exception as e:
                print(f"Failed to play {sound_type} sound: {e}")

    def play_mention(self) -> None:
        """Play mention/highlight sound"""
        self.play("mention")

    def play_message(self) -> None:
        """Play new message sound"""
        self.play("message")

    def play_join(self) -> None:
        """Play user join sound"""
        self.play("join")

    def play_part(self) -> None:
        """Play user part sound"""
        self.play("part")

    def play_notice(self) -> None:
        """Play notice sound"""
        self.play("notice")

    def reload_sounds(self) -> None:
        """Reload sound files (useful after config changes)"""
        if self.initialized:
            # Clean up existing players
            for player in self.players.values():
                if player:
                    player.set_state(Gst.State.NULL)
                    # Remove bus signal watch
                    bus = player.get_bus()
                    bus.remove_signal_watch()

            self.sounds.clear()
            self.players.clear()
            self._load_sounds()

    def set_volume(self, sound_type: str, volume: float) -> None:
        """
        Set volume for a specific sound

        Args:
            sound_type: Type of sound
            volume: Volume level (0.0 to 1.0)
        """
        if not self.initialized:
            return

        player = self.players.get(sound_type)
        if player:
            # Clamp volume to 0.0-1.0
            clamped_volume = max(0.0, min(1.0, volume))
            player.set_property("volume", clamped_volume)

    def set_global_volume(self, volume: float) -> None:
        """
        Set volume for all sounds

        Args:
            volume: Volume level (0.0 to 1.0)
        """
        clamped_volume = max(0.0, min(1.0, volume))
        for player in self.players.values():
            if player:
                player.set_property("volume", clamped_volume)

    def cleanup(self) -> None:
        """Clean up sound resources"""
        if self.initialized:
            try:
                # Stop and cleanup all players
                for player in self.players.values():
                    if player:
                        player.set_state(Gst.State.NULL)
                        # Remove bus signal watch
                        bus = player.get_bus()
                        bus.remove_signal_watch()

                self.players.clear()
                self.sounds.clear()
                self.initialized = False
            except Exception as e:
                print(f"Error during sound cleanup: {e}")


# Simple test beep generator for creating default sound files
def generate_test_sounds():
    """
    Generate simple beep sounds for testing
    Requires numpy and scipy (optional dependencies)
    """
    try:
        import numpy as np
        from scipy.io import wavfile
    except ImportError:
        print("numpy and scipy required for generating test sounds")
        return

    sample_rate = 22050
    duration = 0.2  # seconds

    def generate_beep(frequency: int, filename: str):
        """Generate a simple sine wave beep"""
        t = np.linspace(0, duration, int(sample_rate * duration))
        # Generate sine wave
        wave = np.sin(2 * np.pi * frequency * t)
        # Apply envelope to avoid clicks
        envelope = np.exp(-3 * t)
        wave = wave * envelope
        # Convert to 16-bit PCM
        wave = (wave * 32767).astype(np.int16)
        wavfile.write(filename, sample_rate, wave)

    os.makedirs("sounds", exist_ok=True)

    # Generate different tones for different events
    generate_beep(800, "sounds/mention.wav")  # High pitch for mentions
    generate_beep(600, "sounds/message.wav")  # Medium pitch for messages
    generate_beep(500, "sounds/notice.wav")   # Medium-low for notices
    generate_beep(500, "sounds/join.wav")     # Lower pitch for joins
    generate_beep(400, "sounds/part.wav")     # Lowest pitch for parts

    print("Test sounds generated in sounds/ directory")


if __name__ == "__main__":
    # Test sound manager
    from config_manager import ConfigManager

    # Try to generate test sounds
    try:
        generate_test_sounds()
    except Exception as e:
        print(f"Could not generate test sounds: {e}")

    # Test sound manager
    config = ConfigManager("test_config.json")
    sound_mgr = SoundManager(config)

    if sound_mgr.initialized:
        print("\nTesting sounds...")
        import time

        print("Playing mention sound...")
        sound_mgr.play_mention()
        time.sleep(0.5)

        print("Playing message sound...")
        sound_mgr.play_message()
        time.sleep(0.5)

        print("Playing notice sound...")
        sound_mgr.play_notice()
        time.sleep(0.5)

        print("Playing join sound...")
        sound_mgr.play_join()
        time.sleep(0.5)

        print("Playing part sound...")
        sound_mgr.play_part()
        time.sleep(0.5)

        sound_mgr.cleanup()
    else:
        print("Sound system not initialized")
