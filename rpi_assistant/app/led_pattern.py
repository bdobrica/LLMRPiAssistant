#!/usr/bin/env python

import math
import time


class LedPattern(object):
    def __init__(self, show=None, number=12):
        self.pixels_number = number
        self.pixels = [0] * 4 * number

        if not show or not callable(show):
            def dummy(data):
                pass
            show = dummy

        self.show = show
        self.stop = False

    def wakeup(self, direction=0):
        """Animated circular sweep from direction."""
        position = int((direction + 15) / (360 / self.pixels_number)) % self.pixels_number
        
        # Sweep animation - expanding circle from position
        for radius in range(0, self.pixels_number // 2 + 1):
            if self.stop:
                break
            pixels = [0] * 4 * self.pixels_number
            
            for i in range(self.pixels_number):
                # Calculate distance from position
                dist = min(abs(i - position), self.pixels_number - abs(i - position))
                
                if dist <= radius:
                    # Gradient based on distance
                    brightness = int(60 * (1 - dist / (radius + 1)))
                    pixels[i * 4 + 1] = brightness  # Green
                    pixels[i * 4 + 2] = brightness // 2  # Blue
            
            self.show(pixels)
            time.sleep(0.05)
        
        # Hold final state briefly
        time.sleep(0.3)

    def listen(self):
        """Gentle breathing blue effect."""
        # Start with a gentle pulse for smooth transition
        for _ in range(3):
            if self.stop:
                break
            # Breathe in
            for brightness in range(16, 40, 2):
                if self.stop:
                    break
                pixels = [0, 0, 0, brightness] * self.pixels_number
                self.show(pixels)
                time.sleep(0.03)
            # Breathe out
            for brightness in range(38, 15, -2):
                if self.stop:
                    break
                pixels = [0, 0, 0, brightness] * self.pixels_number
                self.show(pixels)
                time.sleep(0.03)
        
        # Settle to steady state
        pixels = [0, 0, 0, 24] * self.pixels_number
        self.show(pixels)

    def think(self):
        """Smooth rotating gradient with pulsing effect."""
        angle = 0
        pulse_phase = 0
        
        while not self.stop:
            pixels = [0] * 4 * self.pixels_number
            
            # Pulsing brightness
            pulse = 0.5 + 0.5 * math.sin(pulse_phase)
            
            for i in range(self.pixels_number):
                # Rotating gradient
                led_angle = (i / self.pixels_number) * 2 * math.pi
                wave = (math.sin(led_angle + angle) + 1) / 2
                
                # Cyan with pulsing brightness
                green = int(24 * wave * pulse)
                blue = int(32 * wave * pulse)
                
                pixels[i * 4 + 1] = green  # Green
                pixels[i * 4 + 2] = blue   # Blue
            
            self.show(pixels)
            angle += 0.15
            pulse_phase += 0.08
            time.sleep(0.04)

    def speak(self):
        """Smooth audio-like visualization with wave propagation."""
        phase = 0
        
        while not self.stop:
            pixels = [0] * 4 * self.pixels_number
            
            for i in range(self.pixels_number):
                # Create wave pattern
                led_phase = (i / self.pixels_number) * 2 * math.pi
                intensity = (math.sin(led_phase + phase) + 1) / 2
                
                # Greenish speaking color
                green = int(48 * intensity)
                blue = int(20 * intensity)
                
                pixels[i * 4 + 1] = green
                pixels[i * 4 + 2] = blue
            
            self.show(pixels)
            phase += 0.25
            time.sleep(0.03)

    def offline(self):
        """Red pulsing effect for offline/error state."""
        # Gentle red pulse
        while not self.stop:
            # Pulse in
            for brightness in range(16, 50, 2):
                if self.stop:
                    break
                pixels = [0, brightness, 0, 0] * self.pixels_number  # Red channel
                self.show(pixels)
                time.sleep(0.03)
            # Pulse out
            for brightness in range(48, 15, -2):
                if self.stop:
                    break
                pixels = [0, brightness, 0, 0] * self.pixels_number  # Red channel
                self.show(pixels)
                time.sleep(0.03)

    def off(self):
        self.show([0] * 4 * self.pixels_number)
