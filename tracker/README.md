# Local checkpoint tracker

For DreamHost shared hosting and the static `/mdr/moreau/` page, use the
[cron publisher instructions](../deploy/DREAMHOST.md). This page describes the
continuous local test server, which remains available for development.

This is a local prototype for reading checkpoint reports from a Google Doc or a
text file. It uses the Moreau course with six **fictional** runners. The configured
09:00 start is for testing only. No movie renderer or DEC-report code is involved.

Python 3.11+ is required. No third-party Python
packages, Node installation, or paid services are required for this prototype.
Run commands from the Git checkout root.

## Start with your Google Doc

For the simplest test, use only fictional data in the document, then set Google
Doc **Share > General access > Anyone with the link > Viewer**. The app only reads
the doc; people typing reports still use their normal editing access. The app does
not change the document's sharing settings. Link-viewable export availability is
checked at runtime; if Google refuses access, use the private-doc API option below.

```sh
python3 -m tracker.server --source google --google-doc 'YOUR_GOOGLE_DOC_URL'
```

Supply a document ID/full URL with `--google-doc`, or set `TRACKER_GOOGLE_DOC` in the environment.

Open **http://localhost:8000** in your browser. Enter the report lines from
[`test-script.md`](../races/moreau-test/test-script.md) into the Google Doc, one
step at a time. The source is polled every 15 seconds; the browser refreshes its
data every three seconds. No page reload is necessary.

For a different document, supply `--google-doc 'https://docs.google.com/document/d/ID/edit'`.
If port 8000 is occupied, add `--port 8001` and open that port instead.

## File-only test (works without Google or internet)

```sh
python3 -m tracker.server --source file
```

Open the same webpage. Append report lines to `races/moreau-test/live-log.txt` and
save the file. Use a separate database if you want to compare the file and Google
tests independently:

```sh
python3 -m tracker.server --source file --database outputs/tracker/file-test.sqlite3
```

Stop a running server with Ctrl+C before starting the other mode on the same port.
Inputs use the same source identity, so switching input modes on the same database
keeps prior reports. Use different databases for separate test sessions.

## Reports and corrections

### Clock behavior

The default `latest_report` clock advances when the next report arrives. It is
intentionally stationary between reports, letting you rehearse the fictional race
without waiting for real time. For a continuously ticking clock, use `--clock live`.
It counts from the configuration's actual start date and time, stays at zero before
the start, and does not change when checkpoint reports arrive. Confirm the race-day
start before using live mode: the example October 31, 09:00 start is fictional.

### UltraSignup roster import

Download the participant/registration export from UltraSignup after assigning bibs.
CSV and XLSX are supported. Import it with:

```sh
python3 -m tracker.import_roster 'MoreauExport.xlsx' --output races/moreau-2026/roster.json
```

The importer saves only names and bib numbers. It rejects conflicting duplicate bibs,
skips rows marked removed and reports registrations without bibs. Registration alone
does not mark a runner as started. A later export merges additions and retains existing runners missing from that
export. The next cron publish loads it; restart a continuous server afterward. A changed name on an existing bib requires explicit review.

Load an imported roster with `--roster races/moreau-2026/roster.json` or set
`roster_file` in the race configuration (relative to that config's directory).
Use the actual Moreau race configuration and a separate database when switching to
real runners; preserve the current six-runner test so its scripted reports still work.

### Race director commands and late runners

Use the separate [director log](../deploy/DIRECTOR-LOG.md) for ADD, DNS, UNDO DNS,
PASS, FINISH and WITHDRAW commands. No edits to the radio team's workflow are
needed. Add `--director-doc URL` to the server or publisher command, or configure
`TRACKER_DIRECTOR_DOC` in the DreamHost environment. `--director-log FILE` provides
an offline file alternative. Each source's health and last successful read are
independent.

Director additions persist in the SQLite database and survive later UltraSignup
imports. The next poll rechecks unknown-bib radio messages. Director corrections
supersede matching radio reports; originals remain in the audit. DNS takes
precedence until UNDO DNS. Append commands; deleting a line does not retract it.

If the RD document is unavailable, a hosting-shell alternative is
`python3 -m tracker.add_runner`: it prompts for bib/name and adds to the existing
roster JSON. A subsequent roster import merges additions and preserves existing
runners; reassignment is rejected. Updates are atomic, with a `.bak` of the prior
file. The next cron publish loads file additions; continuous servers need a restart
for changes to the roster file (RD additions work without a restart).

### Existing radio operators' TIME / MESSAGE table

The tracker automatically recognizes the two-column table used at Buck 50 and
Moreau. Operators can keep using their existing document and wording. Public
Google Docs are read as HTML so cell boundaries and multiline messages survive;
the authenticated API reader preserves the same rows. Existing ID/pipe documents
continue to work.

Examples (separate TIME and MESSAGE cells):

| TIME | MESSAGE |
|---|---|
| 0910 | Checkpoint A Bib #101 passing location |
| 0935 | Checkpoint B #101 passed at 0930, #102 and #103 at 0932 |
| 0950 | Checkpoint C First female runner #104 passed location bib #105 dropped from race |
| 1100 | Finish Line Bib #101 finished the race at 1058 |

Both HHMM and HH:MM times work. Explicit passage times take precedence over the
TIME cell; otherwise that cell supplies the report time, which may be later than
actual passage. The roster and configured checkpoints validate each report.
A withdrawal without an explicit location changes status while preserving any
last known checkpoint; it does not place the runner at the reporting station.

Routine radio/sweep traffic is ignored. Requests, absent/outstanding runners,
unknown bibs/stations, duplicate bib identities, and ambiguous corrections go to
private review. Explicit passage times up to two minutes ahead of the report clock
are accepted with a clock warning; larger discrepancies are held. Separate prose
corrections are flagged rather than guessed: a director can correct the original
table row after checking the radio log. No official results or race-specific bib
exceptions are used to infer progress.

Rows get internal IDs stored in SQLite, so repeated polls and restarts do not
create duplicates. Editing an identifiable row replaces its entire runner group
and retains audit history. Invalid/incomplete edits retain the last accepted
version. Inserting rows and appending reports preserve existing identities;
deleting an accepted row retains its observations and raises a review issue.
Several simultaneous edits whose row identities cannot be matched stop that
update with a source error, preserving the previously confirmed data.

For a fictional file test, independent of your existing test database:

```sh
python3 -m tracker.server --source file --log races/moreau-test/radio-log.txt --database outputs/tracker/radio-test.sqlite3
```

The example has six fictional runners, five finishes and one withdrawal. It uses
the same natural wording as the operators; change a row and save to try corrections.
For a live Google Doc, the server/publisher commands and cron schedule are unchanged.
Use the real roster, confirmed start and a separate database before switching from
fictional testing to the actual Moreau log.

The local staff view shows issues and progression conflicts. The static spectator
site hides private radio text. The cron log prints review counts; inspect its
input reports privately on the hosting shell:

```sh
python3 -m tracker.review --database "$HOME/mdr-tracker-data/moreau-test.sqlite3"
```

Use the actual database path from your environment file for race day. This command
is read-only and never changes observations. Repeated-checkpoint courses such as
Buck's return leg still need a separate course-visit model; this adapter does not
add lap/return-visit support.

### Structured report syntax (also supported)


```text
T001 | 09:10 | A | 101 | PASS
T002 | 09:12 | A | 102,103 | PASS
T003 | 09:38 | A | 102 | WITHDRAWN
T004 | 11:55 | FINISH | 101 | FINISH
```

Each row has an ID, actual event time, checkpoint, bib(s), and action. All times are
interpreted on the configured race date in America/New_York. START and FINISH are
special stations. Other stations are read from the course configuration. Blank
lines and lines beginning with # are ignored. Put one report in each paragraph;
formatting a report as a heading or a list is not required.

- **Correct:** edit the original line while keeping the same ID. Both revisions
  remain in the audit log. If a correction is malformed, the last valid version
  stays active and the page shows an issue.
- **Retract:** replace the original line with `T004 | VOID`. Deleting a line alone
  does not retract an accepted observation, preventing partial edits from erasing
  runner data.
- **Late report:** write its actual passage time, even if it is older than the
  last entry. Processing uses event time; the audit also records receipt time.
- **Duplicate ID:** neither occurrence is applied until the ambiguity is fixed.
- Unknown bibs/checkpoints, invalid times and backwards progress are flagged. A
  checkpoint report after a finish or withdrawal is held for review.

The test clock follows the latest valid report rather than the current wall clock.
Runner positions are last confirmed checkpoints, never extrapolated GPS positions.
Finish places are provisional and based on accepted finish reports. A real race
configuration would set `clock_mode` to `live` and use the actual start date/time.

State survives restarts in `outputs/tracker/moreau-local-test.sqlite3`. To start a
fresh session without losing the old audit, pass a new `--database` filename.
The HTTP server binds only to loopback. It is not yet a public or production service.

## Private Google Doc: official API option

Keep the document private if you prefer. The app supports a Google OAuth Desktop
client and read-only Google Docs access, using a local browser sign-in:

1. In Google Cloud Console, create/select a project and enable **Google Docs API**.
2. Configure the Google Auth consent screen/audience. If the app is in testing,
   add your own Google account as a test user.
3. Create an **OAuth client ID > Desktop app**, and download its client JSON.
4. Run the helper, substituting the actual downloaded filename:

```sh
python3 -m tracker.google_auth --client-file '/path/to/client_secret.json'
```

Sign in as an account that can read the document. Then run:

```sh
python3 -m tracker.server --source google --google-doc 'YOUR_GOOGLE_DOC_URL' --google-token tracker/.secrets/google-token.json
```

The token file stays on your machine and is excluded from Git. Do not upload it or
paste its contents into chat. Read-only Docs authorization can read documents the
signed-in account can access; the tracker requests only the configured document.
Testing-mode OAuth grants may expire and require sign-in again. The helper and
private API path need a live Google account to verify end to end.

## Code boundaries and current limits

- `core.py`: race config, validation, corrections, SQLite history, confirmed state.
- `director.py`: director commands, persistent additions, DNS and explicit overrides.
- `roster.py`: atomic additive file-roster updates and bib reassignment checks.
- `radio.py`: table-row identities and conservative natural radio-message parsing.
- `sources.py`: Google Doc and text extraction. Another input adapter can feed the
  same observations later.
- `server.py`: polling and local read-only HTTP endpoints.
- `web/`: course map, runner table, activity and source/validation status.
- `races/moreau-test/`: fictional roster and typing script.

This prototype supports a single visit to each checkpoint and a single-day race.
Repeated checkpoint visits/laps, operator entry pages and offline queues, independent
source merging, authentication for staff, production hosting, and radio transcription
remain future work. Do not use the local prototype as the sole runner-accountability
system on race day; retain the operators' source log.

## Checks

The full suite includes the original Buck 50 radio table as an offline regression.
Run it alone with `python3 -m unittest tracker.tests.test_buck50 -v`.
See the [fixture notes](tests/fixtures/buck50/README.md) for expected outcomes and
the distinction between message parsing and repeated course visits.


```sh
python3 -m unittest discover -s tracker/tests -v
node --check tracker/web/app.js
node --test tracker/tests/test_clock.cjs
```
