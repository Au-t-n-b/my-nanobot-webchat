# Tool Usage Notes

Tool signatures are provided automatically via function calling.
This file documents non-obvious constraints and usage patterns.

## exec — Safety Limits

- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- `restrictToWorkspace` config can limit file access to the workspace

## cron — Scheduled Reminders

- Please refer to cron skill for usage.

## Remote Browser — Live Web View

When you need to show the user a web page or demonstrate browser-based operations in real time, output a Markdown link in this exact format:

```
[实时浏览](browser://https://target-url.com)
```

The user's AGUI will open a live interactive browser panel on the right side, streaming screenshots from the backend Playwright instance. The user can click and scroll within that panel to interact with the page.

### AUTO_OPEN — Automatic Panel Activation

If you are executing a task that involves web collaboration (e.g., navigating a site, filling a form, scraping data) and you want the browser panel to open **automatically** without requiring the user to click, include the following marker **once** in your reply:

```
[AUTO_OPEN](browser://https://target-url.com)
```

Guidelines:
- Use `[AUTO_OPEN]` at most **once per reply**, at the start of the step where the browser work begins.
- After the panel is open, use regular `[实时浏览](browser://...)` links for subsequent references.
- Do **not** use `[AUTO_OPEN]` for purely informational replies that do not involve real-time browser interaction.
