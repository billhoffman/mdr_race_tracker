# DreamHost shared hosting: scheduled static publishing

Target URL: **https://www.llamasystem.org/mdr/moreau/**

Already running the test? The [Moreau race-day runbook](MOREAU-RACE-DAY.md)
covers SSH login, the 1Password reference, importing actual bibs/names, and switching
the existing cron job from fictional test data to the real race.

This mode runs briefly from cron, reads the Google Doc, updates the private SQLite
database, publishes static spectator files, and exits. DreamHost serves the files
normally. It does not run a persistent process, listen on a port, need a reverse
proxy, or require root/systemd. The continuous local server still works for testing.

Every cron run reads the current log, with stable IDs preventing duplicates. The
page polls the published state every three seconds; new observations appear after
the next cron run, typically within about a minute plus source/network delay.
The live race clock ticks in the browser between publications. The fictional test
clock still advances only with reports.

## 1. Update and check Python

On DreamHost, from your SSH session:

```sh
cd ~/mdr_race_tracker
git pull --ff-only
python3 --version
command -v python3
python3 -m unittest discover -s tracker/tests -v
```

Use Python 3.11+. If the default is older, check whether `python3.11` or `python3.12`
is available. Set the actual executable path in the environment file below. If
none is available, stop here and share the version output so we can choose a path.

## 2. Configure paths and document access

```sh
cp deploy/dreamhost.env.example "$HOME/.mdr-tracker.env"
chmod 600 "$HOME/.mdr-tracker.env"
nano "$HOME/.mdr-tracker.env"
```

Set `TRACKER_GOOGLE_DOC` to the same fictional Google Doc used locally. For the
link-viewable input, it must allow **Anyone with the link > Viewer**. A private
Doc can instead use the optional OAuth token described in `tracker/README.md`.

Confirm the site's **actual web directory** in DreamHost. If it is
`/home/dh_6n4gzz/llamasystem.org`, the configured output path is:

```text
/home/dh_6n4gzz/llamasystem.org/mdr/moreau
```

If DreamHost shows a different website directory, change `TRACKER_WEB_ROOT` to
that path plus `/mdr/moreau`. The directory should be new/empty. Publishing refuses
to overwrite an existing unrelated website. Leave the existing homepage and sibling
directories alone.

Keep `TRACKER_DATABASE`, Google token files and the Git checkout outside the public
website directory. The publisher enforces database/token placement. The default
database uses `~/mdr-tracker-data/`, not `~/llamasystem.org/`.

## 3. Run one publication manually

```sh
sh deploy/dreamhost-publish.sh
```

Visit **https://www.llamasystem.org/mdr/moreau/**, with the trailing slash. A first
publication may contain an empty test race until reports arrive. If source access
fails, the output includes a source-error message and any previously confirmed data.
The script exits nonzero on input failures so cron logs record the problem.

Enter a line from `races/moreau-test/test-script.md`, run the command again, and
refresh the webpage. This confirms the Google fetch and hosting paths before cron.

## 4. Schedule once per minute

In DreamHost's Cron Jobs page, select the same SSH user, **dh_6n4gzz**. Use:

```sh
/bin/sh /home/dh_6n4gzz/mdr_race_tracker/deploy/dreamhost-publish.sh
```

Schedule every minute, every hour, every day. If the panel does not offer every
minute, use DreamHost's supported SSH crontab editor:

```sh
crontab -e
```

Add this line without removing existing jobs:

```cron
* * * * * /bin/sh /home/dh_6n4gzz/mdr_race_tracker/deploy/dreamhost-publish.sh
```

Use either the panel entry OR crontab entry, not both. The publisher takes a lock
to prevent overlapping cron runs from writing the same database. A Google read
has a timeout; the job does not sleep or poll continuously. To log output privately,
create `~/mdr-tracker-data/` and append this to the command:

```sh
>> /home/dh_6n4gzz/mdr-tracker-data/publish.log 2>&1
```

Cron is best-effort and may run late; do not assume exactly 60-second delivery.
The page displays its last successful source read and flags delayed updates.

## 5. Real Moreau race

Keep the fictional test until ready. Prepare `race.local.json` with the confirmed
date, actual start, `clock_mode: "live"`, `test_mode: false`, the Moreau course, and
a distinct race ID. Import the roster and set the commented `TRACKER_CONFIG` and
`TRACKER_ROSTER` lines in the environment file. Choose a new database for real data.

The existing output directory is tagged with its race ID to prevent an accidental
cross-race overwrite. To switch it from the fictional race to the real one, pause
the cron entry, rename the existing `moreau` output folder to `moreau-test`, then
publish the real race to the newly empty `moreau` path. Retain the test database;
restart the cron entry after verifying the real page.

## What becomes public

Only HTML/CSS/JS, the course, and a sanitized spectator state are published. The
SQLite database, original source text, invalid-line details, raw audit history and
Google token are not exported. Runner names and confirmed passage/finish/withdrawal
status are intentionally public. Assets use relative links so `/mdr/moreau/` works
without changes to the rest of the website.

Source failures preserve previously confirmed runner observations. Writes replace
complete files atomically; hashed course/assets prevent partial-update mismatches.
Published files don't include private audit endpoints. Old hashed asset versions
are retained so already-open pages keep working during updates.
