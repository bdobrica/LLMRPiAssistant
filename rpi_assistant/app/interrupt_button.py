"""Optional ReSpeaker button: stop a spoken answer, then accept a correction."""


def open_interrupt_button(recording_config, playback, controls=None):
    if recording_config.interrupt_button_gpio < 0:
        return None
    from gpiozero import Button

    button = Button(recording_config.interrupt_button_gpio, pull_up=True, bounce_time=0.1)
    button.when_pressed = controls.button_press if controls else playback.interrupt
    if controls:
        button.hold_time = 1.5
        button.hold_repeat = False
        button.when_held = controls.button_hold
    print(f"Answer interruption button enabled on BCM GPIO{recording_config.interrupt_button_gpio}.")
    return button
