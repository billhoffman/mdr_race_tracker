# Mountain Dog Running Race Tracker

A checkpoint-based race tracker with a browser map, runner table, Google Doc or
file ingestion, and an auditable SQLite history. It requires **Python 3.11+** and
the Python standard library; there are no application packages to install.

The bundled example uses the Moreau course and six fictional runners. Course files
and race settings are separate from the code. Movies, post-event reports, original
registration exports and private runner contact information are not part of this repo.

## Clone and run

```sh
git clone git@github.com:billhoffman/mdr_race_tracker.git
cd mdr_race_tracker
python3 -m tracker.server --source file
```

Open <http://localhost:8000>. Add reports to `races/moreau-test/live-log.txt`, using
the steps in [the typing script](races/moreau-test/test-script.md).

For the shared Google Doc, supply its ID or full URL:

```sh
python3 -m tracker.server --source google --google-doc 'YOUR_GOOGLE_DOC_URL'
```

Or set `TRACKER_GOOGLE_DOC` in the server environment. The document ID, credentials
and the local test database are not copied from the original workspace into Git.
For public/link-viewable fictional docs, text export needs no sign-in. For private
docs, use the [optional Google OAuth setup](tracker/README.md#private-google-doc-official-api-option).
The server reads every 15 seconds; the page refreshes data every three seconds.

## Server deployment

### DreamHost shared hosting

Shared hosting is supported through the **one-shot static publisher**, run by cron
about once per minute. It reads the log, updates the private database, publishes
the spectator page, and exits. No persistent server or reverse proxy is needed.

See [the DreamHost setup](deploy/DREAMHOST.md) for publishing to
**https://www.llamasystem.org/mdr/moreau/**. The live race clock ticks in the browser
between cron updates. New observations appear after the next scheduled run.

For SSH access, the 1Password reference, UltraSignup roster import and switching
from the current test to the actual race, use the
[Moreau race-day runbook](deploy/MOREAU-RACE-DAY.md).

### Hosts supporting long-running services

This is a long-running Python application: the host needs Python process support,
outbound HTTPS to Google, and a writable persistent directory. Static-only hosting
or a host that only supports PHP will not run it by itself.

Keep the database **outside the Git checkout**, so updates and replacements of
the code cannot erase it. For example, on a Linux server with a pre-created,
writable `/var/lib/mdr-race-tracker` directory:

```sh
python3 -m tracker.server \
  --source google \
  --google-doc 'YOUR_GOOGLE_DOC_URL' \
  --database /var/lib/mdr-race-tracker/moreau-test.sqlite3 \
  --public
```

By default it listens on `127.0.0.1:8000`. Configure your existing web server's
HTTPS reverse proxy to forward requests to that address. Example configuration
fragments are in [deploy/](deploy/). Use a **dedicated hostname**, such as
`tracker.example.com`, because the browser uses root-relative `/api/` paths.
The main website can link to that hostname. For an existing site's subdirectory,
use the static publisher above instead.

`--public` hides raw operator history and validation details and disables
`/api/audit`. Staff mode is the default local view; protect it using your host's
access controls if exposing it remotely. The prototype uses Python's built-in
HTTP server behind the proxy; it has not been load-tested for a large public audience.

Keep the Python process running with a supervisor (for example systemd), rather
than relying on a terminal session staying open. `/healthz` checks process readiness;
source freshness and connection errors remain visible in `/api/state` and the page.

For direct container/network access, use `--host 0.0.0.0 --port 8000` and your
host's normal proxy/firewall configuration. The default remains loopback.

## Real race setup

1. Run `python3 -m tracker.setup_race` and answer the date/start-time prompts.
   This creates the real race configuration and handles the New York timezone.
2. Review the displayed start time. The old fictional test start is not reused.
3. Import the UltraSignup participant export after assigning bib numbers:

```sh
python3 -m tracker.import_roster 'MoreauExport.xlsx' --output races/moreau-2026/roster.json
```

4. Run with the real config, imported roster, and a separate persistent database:

```sh
python3 -m tracker.server \
  --config races/moreau-2026/race.local.json \
  --roster races/moreau-2026/roster.json \
  --source google --google-doc 'YOUR_RACE_DOC_URL' \
  --database /var/lib/mdr-race-tracker/moreau-2026.sqlite3 \
  --public
```

Registration does not imply a runner has started. START or checkpoint reports
provide evidence of participation. Keep staff's original radio/aid-station log as
the authoritative source. Single-day, single-visit checkpoint courses are supported
in this prototype; laps/repeated visits and offline station entry are future work.

## Updates and checks

Stop the process before changing roster/config or updating code. Back up the
persistent database, pull the changes, run tests, then restart the service.

```sh
git pull --ff-only
python3 -m unittest discover -s tracker/tests -v
```

If Node is available, `node --check tracker/web/app.js` checks browser JS syntax.
Node is not required to run the tracker. Full local testing instructions are in
[tracker/README.md](tracker/README.md).
