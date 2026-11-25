
import queue
import threading
import time

from gpiozero import LED

from .apa102 import APA102
from .led_pattern import LedPattern


class Pixels:
    PIXELS_N = 12

    def __init__(self, pattern=LedPattern, num_pixels=None):
        self.PIXELS_N = num_pixels if num_pixels is not None else self.PIXELS_N
        self.pattern = pattern(show=self.show, number=self.PIXELS_N)

        self.dev = APA102(num_led=self.PIXELS_N)
        
        self.power = LED(5)
        self.power.on()

        self._indicator_lock = threading.Lock()
        self.muted = False
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

        self.last_direction = None

    def wakeup(self, direction=0):
        self.last_direction = direction
        def f():
            self.pattern.wakeup(direction)

        self.put(f)

    def listen(self):
        if self.last_direction:
            def f():
                self.pattern.wakeup(self.last_direction)
            self.put(f)
        else:
            self.put(self.pattern.listen)

    def follow_up(self):
        self.put(self.pattern.follow_up)

    def think(self):
        self.put(self.pattern.think)

    def speak(self):
        self.put(self.pattern.speak)

    def offline(self):
        self.put(self.pattern.offline)

    def off(self):
        self.put(self.pattern.off)

    def set_muted(self, muted):
        # Update the physical indication synchronously before capture can reopen.
        with self._indicator_lock:
            self.muted = muted
            self._show_data(([0, 32, 0, 0] if muted else [0, 0, 0, 0]) * self.PIXELS_N)
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        # This cue checks the current state when executed; an old mute cue cannot
        # turn the LEDs red after unmute. All animations pass through show().
        self.put(lambda: self.show([0] * 4 * self.PIXELS_N) if self.muted else self.pattern.listen())

    def put(self, func):
        self.pattern.stop = True
        self.queue.put(func)

    def _run(self):
        while True:
            func = self.queue.get()
            self.pattern.stop = False
            func()

    def show(self, data):
        with self._indicator_lock:
            if self.muted:
                data = [0, 32, 0, 0] * self.PIXELS_N
            self._show_data(data)

    def _show_data(self, data):
        for i in range(self.PIXELS_N):
            self.dev.set_pixel(i, int(data[4*i + 1]), int(data[4*i + 2]), int(data[4*i + 3]))

        self.dev.show()

if __name__ == '__main__':
    pixels = Pixels()

    while True:

        try:
            pixels.wakeup()
            time.sleep(3)
            pixels.think()
            time.sleep(3)
            pixels.speak()
            time.sleep(6)
            pixels.off()
            time.sleep(3)
        except KeyboardInterrupt:
            break


    pixels.off()
    time.sleep(1)
