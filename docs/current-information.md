# Current-information answers (F04)

Ask a changing-fact question such as “What's the latest stable Python release?”
or explicitly say “Look that up.” The assistant can use hosted web search, answer
briefly and name the cited source aloud. Ordinary questions such as “What's a
manifold?” do not need a lookup. Follow-ups and button corrections retain context.

## Provider and configuration

```ini
[openai]
web_search_enabled = true
```

Set this to `false` to disable lookup, or use `OPENAI_WEB_SEARCH_ENABLED`; explicit
file settings win. Restart after changing configuration. Disabled lookup tells the
model to acknowledge that current facts cannot be verified.

Lookup uses the existing OpenAI key and `chat_model` (tested: `gpt-6-luna`, SDK
3.58.0), through [Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search).
The [model supports this tool](https://developers.openai.com/api/docs/models/gpt-6-luna).
Normal conversation, app classification and MCP retain their existing Chat
Completions flow. No SecondContext connection, new account, Python dependency or
local browser is required.

The conversation model selects a lookup tool when needed. Each lookup makes one
Responses request with live access enabled, low search context, at most two hosted
tool calls and 700 output tokens. Existing HTTP timeouts and zero automatic retries
apply; this is not a whole-turn deadline. There is no polling or idle search traffic.
OpenAI currently lists search at $10/1,000 calls plus model tokens; normal chat and
speech remain additional costs. Check [current pricing](https://developers.openai.com/api/docs/pricing)
before budgeting. Model selection and source quality still affect results.

## Evidence and uncertainty

- Completed search and valid URL citations are required. Failed, incomplete or
  uncited output produces “I couldn't verify that from current sources” rather than
  a guessed current fact. An unavailable search does not reuse a preceding answer.
- The reader is instructed to prefer primary sources, check publication/event dates,
  and explicitly describe unresolved disagreements or insufficient evidence. Source
  quality, freshness and contradiction detection remain model-dependent; a citation
  is not proof that a claim is correct. Live access does not guarantee every result
  is newly fetched. Retrieval time is distinct from a source's publication date.
- Spoken answers name up to two source domains. Displayed answers preserve Markdown
  links. The existing structured interaction log retains the query, retrieval time,
  original provider-cited answer text (a summary, not a page snapshot), citation
  titles/URLs, up to 20 consulted URLs, provider response
  ID and lookup usage. Consulted URLs are not necessarily cited supporting evidence.
  Logging privacy/retention remains the separate H01 item; no new logging service is
  introduced. Raw pages are not downloaded or stored on the Pi.
- The lookup reader has only read-only web search, with no app/MCP/action tools.
  Its result returns directly as the answer; it cannot trigger another action call
  within that lookup. Co-requested actions are blocked and reported as unperformed;
  ask separately for an action. Retained source summaries are explicitly marked as
  untrusted evidence, and instructions inside retrieved text are never authorization.
- For a local question, supply the city or relevant location. This feature does not
  configure household location or implement the separate weather/timer items.

## Checks and rollback

Run `python -m unittest discover -s tests -v`. The explicit paid check below uses
synthetic/public questions, verifies source metadata and follow-up context, checks
a timeless question makes no search, and prints a controlled synthetic source
disagreement for review. It does not record household audio or play the speaker.

```sh
python scripts/check-web-lookup.py --live --config rpi_assistant/config.ini \
  --speech-output /tmp/lookup-check.wav
aplay -D assistant_wm8960 /tmp/lookup-check.wav
```

On the Pi, try a changing-fact question and contextual follow-up. Confirm clear
spoken attribution and compare the claim against its retained source. Test outage
or missing-evidence feedback separately; model/API checks alone do not validate
the microphone or speaker. Actual results and limits are in TODO.md.

The development device retains F02 and its configuration, plus earlier rollbacks:

```sh
sudo cp /var/backups/rpi-assistant-f04/f02.service /etc/systemd/system/rpi-assistant.service
sudo systemctl daemon-reload
sudo systemctl restart rpi-assistant
```
