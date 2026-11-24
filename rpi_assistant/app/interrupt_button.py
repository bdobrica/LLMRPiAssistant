"""Optional ReSpeaker button: stop a spoken answer, then accept a correction."""


def open_interrupt_button(recording_config, playback):
    if recording_config.interrupt_button_gpio < 0:
        return None
    from gpiozero import Button

    button = Button(recording_config.interrupt_button_gpio, pull_up=True, bounce_time=0.1)
    button.when_pressed = playback.interrupt
    print(f"Answer interruption button enabled on BCM GPIO{recording_config.interrupt_button_gpio}.")
    return button
