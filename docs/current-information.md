# Ask about something that changes

Try **“What's the latest stable Python release?”** Then, during green, ask
**“When was that version released?”** You can also explicitly say **“Look that up.”**
The assistant can search the web and name the source in its spoken answer.
Ordinary explanation questions don't need a search.

## Listen for the source

A lookup answer names up to two source domains. Follow-ups keep the recent answer
and its cited evidence. If the lookup fails or returns no usable citations, the
assistant says it couldn't verify the answer instead of reusing an earlier result.

A citation helps you check a claim; it doesn't guarantee correctness. The model
chooses sources and assesses disagreements, so double-check important facts.
For home forecasts, use the dedicated [weather feature](weather.md).

## Enable or disable search

Search uses your existing OpenAI API key and is enabled in the example config.
It adds search/model charges when used. There is no local browser to install and
no background search while idle. To disable it, edit `rpi_assistant/config.ini`
and restart:

```ini
[openai]
web_search_enabled = false
```

Account access to the configured model and search tool is still required. See
[model configuration](openai-upgrade.md) if normal chat works but lookup fails.

## Keep lookup and actions separate

Ask for information and device actions as separate requests. A lookup can read
sources, but cannot run apps or device tools. Text found on the web is evidence,
not permission to change your assistant.

Conversation/source logging is off by default. If you choose to enable it, source
links and summaries enter the private log too; see [privacy](conversation-privacy.md).

[Back to the guides](README.md)
