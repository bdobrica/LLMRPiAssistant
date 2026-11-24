"""Select the player for generated speech; bundled prompts remain MP3."""


def speech_playback_command(backend: str, device: str, path: str) -> list[str]:
    if backend == "realtime":
        return ["aplay", "-D", device, path]
    if backend == "speech":
        return ["mpg123", "-a", device, path]
    raise ValueError("Unknown speech backend")
