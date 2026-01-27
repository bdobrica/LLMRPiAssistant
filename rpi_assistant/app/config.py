"""Configuration management for RPI Assistant.

Loads configuration from config.ini (if present) with fallback to environment variables.
Config.ini takes precedence over environment variables.
"""
import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AudioConfig:
    """Audio and device configuration."""
    sample_rate: int = 16000
    chunk_size: int = 1280
    channels: int = 4
    mic_channel_index: int = 0
    device_match: str = "seeed"


@dataclass
class WakeWordConfig:
    """Wake word detection configuration."""
    threshold: float = 0.5
    cooldown_seconds: float = 1.0
    models: Optional[list[str]] = None  # None = load all default models


@dataclass
class RecordingConfig:
    """Recording behavior configuration."""
    max_duration_seconds: float = 10.0
    silence_hold_seconds: float = 0.8
    silence_rms_threshold: float = 0.007
    pre_roll_seconds: float = 0.4
    output_path: str = "/tmp/command.wav"


@dataclass
class OpenAIConfig:
    """OpenAI API configuration."""
    api_key: str
    whisper_model: str = "whisper-1"
    chat_model: str = "gpt-4o-mini"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"  # alloy, echo, fable, onyx, nova, shimmer
    system_prompt: str = "You are a helpful voice assistant."
    max_tokens: int = 500
    temperature: float = 0.7


@dataclass
class AudioOutputConfig:
    """Audio output configuration for TTS."""
    enabled: bool = True
    device: str = "hw:0,0"  # ALSA device for playback
    tts_output_path: str = "/tmp/response.mp3"


@dataclass
class LEDConfig:
    """LED configuration."""
    count: int = 12  # Number of LEDs (12 for ReSpeaker 4-Mic, 3 for 2-Mic pHAT)


@dataclass
class LoggingConfig:
    """Logging configuration."""
    log_file: str = "openai_interactions.log"
    log_level: str = "INFO"


@dataclass
class Config:
    """Main configuration container."""
    audio: AudioConfig
    wake_word: WakeWordConfig
    recording: RecordingConfig
    openai: OpenAIConfig
    audio_output: AudioOutputConfig
    led: LEDConfig
    logging: LoggingConfig


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from config.ini or environment variables.
    
    Priority:
    1. config.ini (if exists)
    2. Environment variables
    3. Default values
    
    Args:
        config_path: Path to config.ini file. If None, looks in current directory.
    
    Returns:
        Config object with all settings.
    
    Raises:
        ValueError: If required settings (like OPENAI_API_KEY) are missing.
    """
    # Determine config file path
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
    
    config_file = Path(config_path)
    parser = ConfigParser()
    
    if config_file.exists():
        print(f"Loading configuration from {config_file}")
        parser.read(config_file)
    else:
        print("No config.ini found, using environment variables and defaults")
    
    # Helper function to get value with priority: config.ini > env var > default
    def get_value(section: str, key: str, env_var: str, default=None, value_type=str):
        # First check config.ini
        if parser.has_section(section) and parser.has_option(section, key):
            value = parser.get(section, key)
            if value_type == bool:
                return parser.getboolean(section, key)
            elif value_type == int:
                return parser.getint(section, key)
            elif value_type == float:
                return parser.getfloat(section, key)
            return value
        
        # Then check environment variable
        env_value = os.getenv(env_var)
        if env_value is not None:
            if value_type == bool:
                return env_value.lower() in ('true', '1', 'yes')
            elif value_type == int:
                return int(env_value)
            elif value_type == float:
                return float(env_value)
            return env_value
        
        # Finally use default
        return default
    
    # Load Audio Configuration
    audio = AudioConfig(
        sample_rate=get_value("audio", "sample_rate", "AUDIO_SAMPLE_RATE", 16000, int),
        chunk_size=get_value("audio", "chunk_size", "AUDIO_CHUNK_SIZE", 1280, int),
        channels=get_value("audio", "channels", "AUDIO_CHANNELS", 4, int),
        mic_channel_index=get_value("audio", "mic_channel_index", "AUDIO_MIC_CHANNEL", 0, int),
        device_match=get_value("audio", "device_match", "AUDIO_DEVICE_MATCH", "seeed", str),
    )
    
    # Load Wake Word Configuration
    models_str = get_value("wakeword", "models", "WAKEWORD_MODELS", None, str)
    models_list = None
    if models_str:
        # Parse comma-separated list of models
        models_list = [m.strip() for m in models_str.split(",") if m.strip()]
    
    wake_word = WakeWordConfig(
        threshold=get_value("wakeword", "threshold", "WAKEWORD_THRESHOLD", 0.5, float),
        cooldown_seconds=get_value("wakeword", "cooldown_seconds", "WAKEWORD_COOLDOWN", 1.0, float),
        models=models_list,
    )
    
    # Load Recording Configuration
    recording = RecordingConfig(
        max_duration_seconds=get_value("recording", "max_duration_seconds", "RECORDING_MAX_DURATION", 10.0, float),
        silence_hold_seconds=get_value("recording", "silence_hold_seconds", "RECORDING_SILENCE_HOLD", 0.8, float),
        silence_rms_threshold=get_value("recording", "silence_rms_threshold", "RECORDING_SILENCE_RMS", 0.007, float),
        pre_roll_seconds=get_value("recording", "pre_roll_seconds", "RECORDING_PRE_ROLL", 0.4, float),
        output_path=get_value("recording", "output_path", "RECORDING_OUTPUT_PATH", "/tmp/command.wav", str),
    )
    
    # Load OpenAI Configuration (API key is required)
    api_key = get_value("openai", "api_key", "OPENAI_API_KEY", None, str)
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required. Set it in config.ini [openai] section "
            "or as environment variable OPENAI_API_KEY"
        )
    
    openai_config = OpenAIConfig(
        api_key=api_key,
        whisper_model=get_value("openai", "whisper_model", "OPENAI_WHISPER_MODEL", "whisper-1", str),
        chat_model=get_value("openai", "chat_model", "OPENAI_CHAT_MODEL", "gpt-4o-mini", str),
        tts_model=get_value("openai", "tts_model", "OPENAI_TTS_MODEL", "tts-1", str),
        tts_voice=get_value("openai", "tts_voice", "OPENAI_TTS_VOICE", "alloy", str),
        system_prompt=get_value("openai", "system_prompt", "OPENAI_SYSTEM_PROMPT", 
                                "You are a helpful voice assistant.", str),
        max_tokens=get_value("openai", "max_tokens", "OPENAI_MAX_TOKENS", 500, int),
        temperature=get_value("openai", "temperature", "OPENAI_TEMPERATURE", 0.7, float),
    )
    
    # Load Audio Output Configuration
    audio_output = AudioOutputConfig(
        enabled=get_value("audio_output", "enabled", "AUDIO_OUTPUT_ENABLED", True, bool),
        device=get_value("audio_output", "device", "AUDIO_OUTPUT_DEVICE", "hw:0,0", str),
        tts_output_path=get_value("audio_output", "tts_output_path", "TTS_OUTPUT_PATH", "/tmp/response.mp3", str),
    )
    
    # Load LED Configuration
    led_config = LEDConfig(
        count=get_value("led", "count", "LED_COUNT", 12, int),
    )
    
    # Load Logging Configuration
    logging_config = LoggingConfig(
        log_file=get_value("logging", "log_file", "LOG_FILE", "openai_interactions.log", str),
        log_level=get_value("logging", "log_level", "LOG_LEVEL", "INFO", str),
    )
    
    return Config(
        audio=audio,
        wake_word=wake_word,
        recording=recording,
        openai=openai_config,
        audio_output=audio_output,
        led=led_config,
        logging=logging_config,
    )
