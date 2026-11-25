"""RPI Voice Assistant - Main entry point.

A voice-controlled assistant using:
- OpenWakeWord for wake word detection
- OpenAI GPT-Transcribe for speech transcription
- OpenAI GPT for intelligent responses
- OpenAI Realtime for voice responses
"""
import signal
import os
import sys
import threading
import time
import subprocess
from pathlib import Path

from .app_manager import AppManager
from .app_repository import DEFAULT_APP_REPOSITORY_ROOTS
from .audio import WakeWordRecorder
from .config import load_config
from .connectivity import check_internet_connection
from .logger import InteractionLogger
from .interrupt_button import open_interrupt_button
from .mcp_manager import MCPClientManager
from .openai_client import OpenAIClient
from .playback import AudioPlayback
from .voice_command import VoiceCommandHandler
from .controls import LocalControls
from .control_listener import ControlListeners
from .timers import Timers, TimerAlerts
from .household import Household
from .weather import Weather
from .phone_settings import PhoneSettings
from .settings_trial import SettingsTrial
from .audio_checks import AudioChecks
from .privacy import ConversationPrivacy, quiet_provider_logs
from .rpiface_client import RPiFaceClient

try:
    from .pixels import Pixels
    PIXELS_AVAILABLE = True
except ImportError:
    PIXELS_AVAILABLE = False
    print("Warning: Pixels library not available (requires apa102, gpiozero)")


def main():
    """Main application entry point."""
    os.umask(0o077)
    quiet_provider_logs()
    recorder = None
    pixels = None
    connection_monitor_thread = None
    connection_state = {"online": None, "first_check": True}  # None = unknown, True = online, False = offline
    stop_monitor = threading.Event()
    rpiface = None
    mcp_manager = None
    interrupt_button = None
    controls = None
    control_server = None
    timer_alerts = None

    def cleanup():
        """Cleanup resources before exit."""
        stop_monitor.set()
        if controls is not None and controls.privacy is not None:
            controls.privacy.close()
        if controls is not None and controls.audio_checks is not None:
            controls.audio_checks.close()
        if timer_alerts is not None:
            timer_alerts.close()
        if control_server is not None:
            control_server.close()
        if interrupt_button is not None:
            interrupt_button.close()
        if connection_monitor_thread is not None:
            connection_monitor_thread.join(timeout=2)
        if recorder is not None:
            print("\n🧹 Cleaning up audio resources...")
            recorder.stop()
        if pixels is not None:
            pixels.off()
        if rpiface is not None:
            rpiface.close()
        if mcp_manager is not None:
            mcp_manager.close()

    def signal_handler(signum, frame):
        """Handle termination signals."""
        print(f"\n📡 Received signal {signum}")
        cleanup()
        sys.exit(0)

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    def restart_for_settings(signum, frame):
        # Allow ordinary cleanup. Bound it because a stuck audio stop otherwise
        # prevents systemd from starting the candidate or restoring the old INI.
        fallback = threading.Timer(8, os._exit, args=(75,))
        fallback.daemon = True
        fallback.start()
        sys.exit(75)

    signal.signal(signal.SIGUSR1, restart_for_settings)

    try:
        # Load configuration
        config_path = Path(__file__).resolve().parents[1] / "config.ini"
        trial = SettingsTrial(config_path)
        candidate = trial.begin()
        if candidate is not None:
            trial.watch()
        config = candidate or load_config(allow_missing_api_key=True)
        rpiface = RPiFaceClient(
            base_url=config.rpiface.base_url,
            timeout_seconds=config.rpiface.timeout_seconds,
            enabled=config.rpiface.enabled,
        )
        rpiface.set_state("idle")

        # Initialize components
        logger = InteractionLogger(config.logging)
        mcp_manager = MCPClientManager(config.mcp)
        mcp_manager.start()
        openai_client = OpenAIClient(config.openai, mcp_manager=mcp_manager)
        openai_client.weather = Weather(config.weather)
        repository_roots: list[str | Path] = []
        if config.app_store.default_repository_url:
            repository_roots.append(config.app_store.default_repository_url)
        if config.app_store.use_local_repository_fallback:
            repository_roots.extend(DEFAULT_APP_REPOSITORY_ROOTS)
        app_manager = AppManager(
            repository_roots=repository_roots or None,
            repository_public_key=config.app_store.trusted_public_key,
            require_repository_signature=config.app_store.require_signature,
        )

        # Initialize LED pixels if available
        if PIXELS_AVAILABLE:
            try:
                pixels = Pixels(num_pixels=config.led.count)
                print(f"✨ LED pixels initialized ({config.led.count} LEDs)")
            except Exception as e:
                print(f"Could not initialize pixels ({type(e).__name__})")
                pixels = None

        print("=" * 60)
        print("🤖 RPI Voice Assistant")
        print("=" * 60)

        playback = AudioPlayback(config.audio_output)
        def play_audio_prompt(filename: str):
            if recorder is not None and (recorder.capture_paused or recorder.alert_active or recorder.diagnostic_active):
                return
            if recorder is not None:
                recorder.cancel_follow_up()
            try:
                playback.prompt(filename)
            except Exception as exc:
                print(f"Local prompt unavailable ({type(exc).__name__})")

        def monitor_connection():
            """Monitor internet connection and handle state changes."""
            while not stop_monitor.is_set():
                is_online = check_internet_connection(timeout=3)

                # Check if state changed
                if connection_state["online"] != is_online:
                    was_offline = connection_state["online"] is False
                    connection_state["online"] = is_online

                    if is_online:
                        if was_offline and not connection_state["first_check"]:
                            # Was offline, now online - announce return
                            print("\n✅ Internet connection restored!")
                            if pixels and not (recorder and (recorder.capture_paused or recorder.alert_active or recorder.diagnostic_active)):
                                pixels.listen()
                            play_audio_prompt("online.mp3")
                        elif connection_state["first_check"]:
                            # First check and online - don't announce
                            print("✅ Internet connection OK")
                            if pixels and not (recorder and (recorder.capture_paused or recorder.alert_active or recorder.diagnostic_active)):
                                pixels.listen()
                    else:
                        # Lost connection
                        print("\n⚠️  Internet connection lost!")
                        if pixels and not (recorder and (recorder.capture_paused or recorder.alert_active or recorder.diagnostic_active)):
                            pixels.offline()
                        if not connection_state["first_check"]:
                            play_audio_prompt("offline.mp3")

                    connection_state["first_check"] = False

                # Check every 10 seconds
                stop_monitor.wait(10)

        # Start connection monitoring thread
        connection_monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
        connection_monitor_thread.start()

        handler = VoiceCommandHandler(
            config, openai_client, app_manager, logger, playback, rpiface,
            pixels=pixels, is_online=lambda: connection_state["online"],
        )

        def on_recording_complete(audio_path: str) -> bool:
            return handler.process(
                audio_path, continue_conversation=bool(recorder and recorder.recording_is_follow_up),
            )

        # Start wake word recorder
        recorder = WakeWordRecorder(
            config.audio,
            config.wake_word,
            config.recording,
            on_recording_complete=on_recording_complete,
            on_state_change=rpiface.set_state,
            pixels=pixels,
        )

        controls = LocalControls(config.controls, recorder, playback, openai_client)
        controls.connection_status = lambda: connection_state["online"]
        controls.settings = PhoneSettings(config, config_path, controls)
        controls.audio_checks = AudioChecks(controls)
        controls.privacy = ConversationPrivacy(config, logger, controls)
        controls.privacy.start()
        handler.controls = controls
        timers = Timers(config.timers.state_path, config.timers.alert_seconds)
        openai_client.timers = controls.timers = timers
        household = Household(config.household.state_path, config.household.timezone, config.timers.alert_seconds)
        openai_client.household = controls.household = household
        timer_alerts = TimerAlerts(timers, controls, reminders=household)
        controls.timer_alerts = timer_alerts
        timer_alerts.start()
        try:
            interrupt_button = open_interrupt_button(config.recording, playback, controls)
        except Exception as exc:
            print(f"Control button unavailable ({type(exc).__name__}); local page and voice remain available.")
        if config.controls.enabled:
            control_server = ControlListeners(config.controls, controls)
        def check_restart():
            fields = {tuple(pair) for pair in trial.record["fields"]}
            changed = {s for s, _ in fields}
            if any(section in changed and component.error for section, component in
                   (("controls", controls), ("timers", timers), ("household", household), ("logging", logger))):
                raise RuntimeError("Local storage unavailable")
            if "led" in changed and pixels is None:
                raise RuntimeError("LED initialization failed")
            if ("recording", "interrupt_button_gpio") in fields:
                if config.recording.interrupt_button_gpio >= 0 and interrupt_button is None:
                    raise RuntimeError("Button initialization failed")
            if any(s == "mcp" or s.startswith("mcp.server.") for s in changed) and mcp_manager.discovery_failed:
                raise RuntimeError("MCP discovery failed")
            if fields & {("controls", "mixer_card"), ("controls", "mixer_control")}:
                controls.volume.get()
            if "audio_output" in changed and config.audio_output.enabled:
                subprocess.run(["aplay", "-q", "-D", config.audio_output.device, "-t", "raw",
                                "-f", "S32_LE", "-r", "24000", "-c", "2", "/dev/null"],
                               check=True, timeout=4, capture_output=True)
            if control_server:
                deadline = time.monotonic() + 12
                while not control_server.servers:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Phone listener unavailable")
                    time.sleep(.1)
            trial.finish()

        recorder.start(on_ready=check_restart if candidate is not None else None)

    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"Fatal assistant error ({type(e).__name__}); check configuration and hardware.")
        cleanup()
        sys.exit(1)
    finally:
        # Ensure cleanup happens even if exception wasn't caught
        cleanup()


if __name__ == "__main__":
    main()
