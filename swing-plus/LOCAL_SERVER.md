# Running the tool persistently (macOS)

The tool runs as a **launchd LaunchAgent** — it starts automatically when you log in,
restarts itself if it crashes, and keeps running after you close the terminal or this
chat. No need to keep anything open.

**Open it:** http://localhost:8000

---

## Manage the service

```bash
UID_=$(id -u)

# stop it
launchctl bootout gui/$UID_/io.eephus.swingplus

# start it (also runs automatically at login)
launchctl bootstrap gui/$UID_ ~/Library/LaunchAgents/io.eephus.swingplus.plist

# restart it (after pulling new data / code changes)
launchctl kickstart -k gui/$UID_/io.eephus.swingplus

# is it running?
launchctl print gui/$UID_/io.eephus.swingplus | grep -E "state|pid ="

# view logs
tail -f ~/swing_plus/logs/server.log
```

## After updating data or code
The service does **not** auto-reload (kept off for stability). After re-running
`run_leaderboard.py` / `mlb_decision.py` / etc., restart it:

```bash
launchctl kickstart -k gui/$(id -u)/io.eephus.swingplus
```

## Uninstall
```bash
launchctl bootout gui/$(id -u)/io.eephus.swingplus
rm ~/Library/LaunchAgents/io.eephus.swingplus.plist
```

## Manual one-off run (foreground, with auto-reload for dev)
```bash
cd ~/swing_plus && ./run_local.sh          # plain
# or for development (reloads on code edits):
.venv/bin/uvicorn web.app:app --reload
```

Service definition: `~/Library/LaunchAgents/io.eephus.swingplus.plist`
Launch script: `run_local.sh`
