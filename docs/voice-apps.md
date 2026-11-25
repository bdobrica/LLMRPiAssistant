# Try a voice game

Voice apps add small activities such as rolling dice or playing a party game.
They are optional: normal questions, timers, reminders and Shopping work without
installing an app.

## Start with Dice

1. Say **“Hey Jarvis, install app dice.”** Wait for confirmation.
2. During green, say **“Roll a die.”**
3. Ask **“What was the result?”** to refer to the same roll.

The catalog lists apps you *can* install; it doesn't mean they are installed.
A recognized request for a missing app gives installation guidance. App actions
run locally, but speaking to them still uses cloud transcription and speech output.

## Play a three-question trivia round

Say **“Install app trivia”**, then **“Play trivia.”** Each question has two
choices. During green, say the answer or say **“first”** or **“second.”**
You'll hear the answer and a short fact before the next question. Your score
comes after question three. Say **“repeat”** if you missed a choice.

Say **“pause trivia”** to keep your place, even across a restart.
**“Resume game”** repeats the current question. To go back to ordinary
questions and discard the round, say **“stop game.”**

## Explore the other apps

| Try saying | What it does |
| --- | --- |
| “List available apps” | Lists the catalog |
| “List installed apps” | Shows what's already on your Pi |
| “Install app ask”, then “Play ask” | Starts a conversation-starter game |
| “Install app truth or dare”, then “Play truth or dare” | Starts a multi-turn party game |
| “What game is active?” or “Resume app” | Checks or resumes the active game |
| “Cancel app” or “Stop game” | Leaves the game and returns to ordinary questions |
| “Describe app dice” | Describes the installed app and its source |
| “Upgrade app dice” / “Uninstall app dice” | Updates or removes it |

While a game is active, it may handle your next sentence. Cancel it before asking
an unrelated question. Multi-turn apps can save their progress across restart.
A button press stops speech; it doesn't undo a roll or reset a game.

## Install from sources you trust

Apps are Python code running as the assistant's user, not isolated browser games.
The supplied catalog uses signature and checksum verification. Keep those checks
enabled; a rejected download is a reason to investigate, not turn off verification.

If installation fails, check Internet access and try “app store health.” The
checked-out `voice_apps/` catalog can also serve as a local fallback. Installed
bundles live in `~/.config/rpi-assistant/apps/`.

Want to create your own activity? See [extensions](extensions.md). You don't need
the catalog's internal format just to install and play.

[Back to the guides](README.md)
