"""Offline checks for boot configuration changes; no hardware is touched."""

import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "setup_wm8960", Path(__file__).parents[1] / "scripts" / "setup-wm8960.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class AudioSetupTests(unittest.TestCase):
    def test_replaces_legacy_overlay_and_preserves_other_hardware(self):
        source = "dtoverlay=vc4-kms-v3d\ndtoverlay=i2s-mmap\ndtoverlay=seeed-2mic-voicecard\n[pi4]\narm_boost=1\n"
        result = setup.boot_config(source)
        self.assertIn("dtoverlay=vc4-kms-v3d", result)
        self.assertIn("[pi4]\narm_boost=1", result)
        self.assertNotIn("dtoverlay=seeed-2mic-voicecard", result)
        self.assertNotIn("dtoverlay=i2s-mmap", result)
        self.assertTrue(result.endswith("[all]\n" + setup.SPI + "\n" + setup.OVERLAY + "\n"))

    def test_repeated_setup_has_only_one_audio_overlay(self):
        result = setup.boot_config(setup.boot_config("[all]\n"))
        self.assertEqual(result.count(setup.OVERLAY), 1)
        self.assertEqual(setup.boot_config(result), result)

    def test_spi_is_enabled_for_leds_without_vendor_service(self):
        result = setup.boot_config("dtparam=i2c_arm=on\ndtparam=spi=off\n")
        self.assertIn("dtparam=i2c_arm=on", result)
        self.assertNotIn("spi=off", result)
        self.assertEqual(result.count(setup.SPI), 1)

    def test_only_vendor_audio_autoload_entries_are_removed(self):
        source = "i2c-dev\nsnd_soc_ac108 # vendor\nsnd-soc-wm8960\n# keep comment\nspi-dev\n"
        self.assertEqual(setup.module_config(source), "i2c-dev\n# keep comment\nspi-dev\n")

    def test_dkms_override_preserves_other_options(self):
        result = setup.dkms_config('MAKE="custom"\nAUTOINSTALL="yes"\n')
        self.assertIn('MAKE="custom"', result)
        self.assertEqual(result.count("AUTOINSTALL="), 1)
        self.assertIn('AUTOINSTALL="no"', result)

    def test_numeric_wm8960_output_is_stable_after_card_reordering(self):
        original = "[openai]\napi_key = untouched\n[audio_output]\ndevice = hw:1,0\nenabled = true\n"
        updated = setup.assistant_config(original, " 1 [seeed2micvoicec]: simple-card")
        self.assertEqual(updated, original.replace("hw:1,0", setup.PLAYBACK_PCM))
        self.assertEqual(setup.assistant_config(updated, " 0 [seeed2micvoicec]: simple-card"), updated)

    def test_named_output_uses_32_bit_pcm_to_match_live_capture(self):
        original = "[audio_output]\ndevice = plughw:CARD=seeed2micvoicec,DEV=0\n"
        result = setup.assistant_config(original, " 0 [seeed2micvoicec]: simple-card")
        self.assertIn("device = " + setup.PLAYBACK_PCM, result)
        self.assertIn("format S32_LE", setup.PLAYBACK_CONFIG)
        self.assertIn('pcm "hw:CARD=seeed2micvoicec,DEV=0"', setup.PLAYBACK_CONFIG)

    def test_deliberately_selected_other_output_is_preserved(self):
        original = "[audio_output]\ndevice = hw:0,0\n"
        self.assertEqual(setup.assistant_config(original, " 1 [seeed2micvoicec]: simple-card"), original)

    def test_output_comment_and_line_endings_are_preserved(self):
        original = "[audio_output]\r\ndevice = hw:1,0 # speaker\r\nenabled = true\r\n"
        result = setup.assistant_config(original, " 1 [seeed2micvoicec]: simple-card")
        self.assertEqual(result, original.replace("hw:1,0", setup.PLAYBACK_PCM))


if __name__ == "__main__":
    unittest.main()
