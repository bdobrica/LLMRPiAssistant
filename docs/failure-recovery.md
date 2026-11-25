# When a request doesn't work

If the assistant hears no usable words, it plays **“I didn't catch that.”**
If an answer cannot be completed, it plays **“Sorry, I couldn't finish the reply.”**
A detected Internet outage uses the offline announcement. These short clips are
stored on the Pi; explaining a failure needs no cloud call.

## Try again

During a game, **“Could you repeat your answer?”** means the same question
is waiting. Speak again when the lights turn green. If you hear the wake-word
prompt instead, wait for blue and use the wake word. Say **“resume game”**
to hear the question again. Provider failures also return to blue.

If you requested an action, check whether it happened before repeating it. A timer
may have been saved even though speech generation failed. The assistant does not
automatically retry actions or undo a completed action when you press Stop.

During an Internet outage, [phone controls](local-controls.md), saved lists and
local alerts remain available while Wi-Fi/LAN still works. Spoken questions need
Internet. After the online announcement, try a fresh wake-word question.

## If it keeps happening

Try the phone's local microphone/speaker checks. If those pass, check the Internet
status and your provider account/key. “Configured” means a key is saved; it does
not mean the account can use every configured model. See [troubleshooting](troubleshooting.md).

For an unusually slow connection, request limits are configurable:

```ini
[openai]
request_timeout_seconds = 20
tts_timeout_seconds = 30
```

Restart after manual edits. The first is a network-operation timeout, not a total
turn limit; a turn can make several requests. The second limits Realtime speech
generation. Time spent waiting for the speaker pipe to accept audio is charged
to the playback deadline. Each streamed answer is capped at 120 seconds of PCM.
Automatic provider retries are disabled. Increasing waits will not fix
an invalid key or disconnected network.

If the speaker fails, a spoken error is impossible; use the phone status and logs
to investigate. A service restart can currently take about 90 seconds because of
a known shutdown delay—allow it to finish before retrying.

[Back to the guides](README.md)
