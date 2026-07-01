# MCP Server Setup

Two ready-to-run MCP servers live here:

- `gdelt/` — global adverse-news search, no API key needed
- `opensanctions/` — sanctions/PEP/watchlist screening, needs a free API key

Both use the official Python MCP SDK (`FastMCP`) over stdio transport, which
is what Claude Desktop and Claude Code expect.

## 1. Install dependencies

```bash
cd mcp-servers/gdelt && pip install -r requirements.txt
cd ../opensanctions && pip install -r requirements.txt
```

## 2. Get an OpenSanctions API key (free) and store it in a .env file

Sign up at https://www.opensanctions.org/api/. Free keys are issued to
journalists, anti-corruption researchers, and academic projects on request —
mention your use case when you sign up. Businesses/commercial use requires a
separate data license; check current terms on their site since this changes.

Copy the example env file and fill in your real key:

```bash
cd mcp-servers/opensanctions
cp .env.example .env
```

Edit `.env` so it contains:

```
OPENSANCTIONS_API_KEY=your-real-key-here
```

`server.py` loads this `.env` automatically on startup (via `python-dotenv`),
using the script's own directory — so it works no matter what folder the
MCP client launches it from. `.env` is already listed in `.gitignore`, so it
won't get committed if you put this whole bundle under version control.

You do **not** need to `export` the variable manually or put it in the MCP
config JSON — the `.env` file is the single source of truth. If you ever
rotate the key, just edit that one file.

## 3. Register the servers with Claude Desktop / Claude Code

Add to your MCP config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gdelt": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp-servers/gdelt/server.py"]
    },
    "opensanctions": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp-servers/opensanctions/server.py"]
    }
  }
}
```

No `env` block needed for `opensanctions` anymore — the key comes from its
`.env` file, not this config. That also means this config JSON is safe to
back up or share without leaking your key.

Restart Claude Desktop (or reload the Claude Code MCP config) after editing.

## 4. Add the Enigma MCP server (not bundled here)

Enigma runs its own hosted MCP server rather than a self-hosted one. Point
your MCP client at their endpoint using your existing Enigma API key — check
https://documentation.enigma.com for the current MCP connection details,
since hosted endpoint URLs and auth schemes are the kind of thing that
changes without much notice.

## 5. Verify each server works

You can sanity-check either server standalone before wiring it into Claude:

```bash
cd mcp-servers/gdelt
python3 -c "from server import search_news; print(search_news('\"OpenAI\"', timespan='1month', max_records=3))"
```

```bash
cd mcp-servers/opensanctions
# .env should already contain your real OPENSANCTIONS_API_KEY
python3 -c "from server import match_entity; print(match_entity('Gazprom', schema='Company'))"
```

If you get a real JSON response back (not an `{"error": ...}` dict), you're
good to go.

## 6. Install the skill

Copy (or symlink) the `SKILL.md` at the root of this bundle into wherever
your Claude setup looks for skills, alongside these `mcp-servers/`. In
Claude.ai, you can present/upload the `SKILL.md` directly and use the
"Save skill" flow if your org has skill creation enabled.

## Notes on scope and rate limits

- **GDELT**: no published hard rate limit for the free DOC API, but be a
  good citizen — don't hammer it in a tight loop. Full-text search only
  covers roughly the trailing 3 months; older coverage requires other tools
  (web search, EDGAR, news archives).
- **OpenSanctions**: the hosted API meters successful `/match` and `/search`
  calls. Check your usage on your account dashboard. Self-hosting (`yente`)
  is free of per-query metering if you have a bulk data license instead.
- Both APIs' terms of service can change — this bundle was written based on
  their documentation as of mid-2026. Recheck before heavy production use.
