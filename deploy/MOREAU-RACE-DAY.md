# Moreau Half: access, roster import, and race-day setup

Public tracker: **https://www.llamasystem.org/mdr/moreau/**

The site currently runs the fictional six-runner test. These instructions switch
it to the real Moreau race once UltraSignup bibs are available. Keep the test and
real databases separate. Registration is not proof that a runner started.

## Readiness checklist

- [ ] Push the tested code from the Mac, then pull it on DreamHost.
- [ ] Assign 2026 bibs and import the actual 2026 registration roster. Historical
  2020–2025 finish lists are separate reference data, not this race's roster.
- [ ] Run `python3 -m tracker.setup_race` with the confirmed October 31 start time.
- [ ] Set both Google Doc URLs, the real config/roster and a separate real database
  in `~/.mdr-tracker.env`, following the switch steps below.
- [ ] Preserve the fictional test page and publish the real page once. Verify its
  real-race heading, names/bibs, configured start and both connected-source notices.
- [ ] Keep the one-minute cron job active and check `publish.log` after a minute.
- [ ] Rehearse ADD, DNS/UNDO DNS and a correction with the separate offline test
  from [DIRECTOR-LOG.md](DIRECTOR-LOG.md). Keep practice data out of both race Docs.
- [ ] Give race staff editing access to the RD log and link-viewer access to the
  tracker. Ensure radio/timing/check-in staff use the same new bib assignments.
- [ ] Before the start, reconcile attendance and DNS decisions. Registration and
  Not reported do not confirm a runner started. If the actual start changes,
  update the race setup; the radio "Race starting" message does not set the clock.
- [ ] During the race, monitor source freshness and private review. ADD releases
  pending unknown-bib reports automatically on a later successful radio read.

## 1. Log in to DreamHost

From Terminal on your Mac:

```sh
ssh dh_6n4gzz@pdx1-shared-a1-19.dreamhost.com
```

**Password reference:** the DreamHost SSH password for `dh_6n4gzz` is saved in
**1Password**. Retrieve it there when prompted. It is the website/Shell user's
password, which can differ from the DreamHost panel login. No password is stored
in this README or Git repository. Terminal does not display characters as you type.

On DreamHost:

```sh
cd ~/mdr_race_tracker
git pull --ff-only
```

The private data directory and Python installation are already set up on DreamHost.
Use the Python executable already working in `~/.mdr-tracker.env`. The commands
below use `python3`; substitute the configured executable if yours differs.

## 2. Import the UltraSignup roster on your Mac

Assign the runner bibs in UltraSignup, then download its **2026 participant/registration
export**, not historical results. CSV or XLSX is supported. The full export stays
on your Mac; only the generated names-and-bibs JSON goes to DreamHost.

In your Mac Terminal, using the actual export filename:

```sh
cd /Users/hoffman/Running/buck50radio/race-tracker
python3 -m tracker.import_roster "$HOME/Downloads/MoreauExport.xlsx" --output races/moreau-2026/roster.json
```

Check the reported count and skipped rows against the intended race field. Removed
registrations, missing bibs and exact duplicates are skipped. A conflicting name
on an existing bib stops the import. Later imports merge additions and preserve
existing runners. The JSON and its backups are ignored by Git.

## 3. Copy roster.json to DreamHost

Still in the Mac Terminal and repository directory:

```sh
scp races/moreau-2026/roster.json dh_6n4gzz@pdx1-shared-a1-19.dreamhost.com:mdr_race_tracker/races/moreau-2026/roster.json.new
ssh dh_6n4gzz@pdx1-shared-a1-19.dreamhost.com 'mv mdr_race_tracker/races/moreau-2026/roster.json.new mdr_race_tracker/races/moreau-2026/roster.json'
```

Uploading to `.new` and then renaming means cron sees a complete roster file.
The next publish reads the uploaded roster when the real-race environment is active.
Runners initially show **Not reported**; registration does not confirm a start.
There is no need to upload the original export or run the importer on DreamHost.

## 4. Prepare the real race configuration

**Do this later, once the actual start time is confirmed.** There is no need to
run setup today. The existing fictional test website and cron job can keep running
unchanged while you wait. You can also upload/import the roster separately when
it becomes available.

Run the guided setup on DreamHost:

```sh
python3 -m tracker.setup_race
```

It asks for:

1. **Race date** — press Enter to accept October 31, 2026.
2. **Confirmed start time** — type a normal local time, such as `8:00 AM`.
3. **Save?** — review the summary and type `y`.

The time above is an example, not the confirmed start. The helper handles the
New York timezone and writes `races/moreau-2026/race.local.json`. No Python code,
JSON editing or timezone-offset entry is required. Existing setup is backed up
before replacement. This can be done before the roster arrives and does not change
the active test website or cron settings.

Saving a start time does not start the race immediately: the live clock waits
until that configured date and time. If the confirmed time changes, rerun the
setup command to update it. Continue with the race-day Doc and website switch
below only when you are ready to move from the fictional test to the real race.

## 5. Use the radio operators' race Google Doc

Use their existing Moreau TIME / MESSAGE table:

https://docs.google.com/document/d/1tP6AB0TFm3xSzfCjAdRv9Tek6zcI7-6_vIaPBeKtSaA/edit

The operators can keep their normal wording, as at Buck 50. The tracker recognizes
checkpoint names, bib lists, passage times, finishes and drops automatically.
D and G are aid stations. If a message gives an actual passage time, that takes
precedence over the TIME cell; otherwise the radio report time is used.

Keep the fictional test Doc as an archive and use a separate real-race database.
If using link-based access, set **Anyone with the link > Viewer**. Give operators
editing access separately. Do not paste practice reports into the real radio log.
Ambiguous messages and separate prose corrections go to private review; after
checking a correction, the director can edit the original table row. The detailed
[radio table notes](../tracker/README.md#existing-radio-operators-time--message-table)
explain what is accepted and how edits are retained in the audit.

## 6. Pause the test cron entry

On DreamHost:

```sh
crontab -e
```

Below the **END DREAMHOST BLOCK** line, place `#` at the beginning of the tracker
line to pause it. Preserve DreamHost's managed block and any other jobs. The line
should temporarily look like this:

```cron
# * * * * * /bin/sh /home/dh_6n4gzz/mdr_race_tracker/deploy/dreamhost-publish.sh >> /home/dh_6n4gzz/mdr-tracker-data/publish.log 2>&1
```

In nano: **Ctrl+O**, **Enter**, **Ctrl+X**. Confirm with `crontab -l`. Let any
publication already in progress finish before switching settings.

## 7. Switch the environment to the real race

Back up the working test settings, then edit the existing file. Do not copy the
example over it, because that would replace your working paths and Doc setting.

```sh
cp ~/.mdr-tracker.env ~/.mdr-tracker-test.env.backup
chmod 600 ~/.mdr-tracker-test.env.backup
nano ~/.mdr-tracker.env
```

Keep the working REPO, PYTHON and WEB_ROOT values. Set/uncomment these values:

```sh
TRACKER_CONFIG="$TRACKER_REPO/races/moreau-2026/race.local.json"
TRACKER_ROSTER="$TRACKER_REPO/races/moreau-2026/roster.json"
TRACKER_DATABASE="$HOME/mdr-tracker-data/moreau-2026.sqlite3"
TRACKER_GOOGLE_DOC="https://docs.google.com/document/d/1tP6AB0TFm3xSzfCjAdRv9Tek6zcI7-6_vIaPBeKtSaA/edit"
TRACKER_DIRECTOR_DOC="https://docs.google.com/document/d/1wUvZ85JdPXbxxoOp-JBgTGqv2LypBgUackv9q7ktpK4/edit"
```

The first Doc is the radio log; the second is the director command log. Save and exit. The real database
filename is deliberately different from `moreau-test.sqlite3`.

## 8. Preserve the test page and publish the real page

The output folder is tagged with its race ID. Move the test output aside before
publishing a different race to the same URL. This preserves the test page and lets
the publisher create a new `moreau` folder:

```sh
mv "$HOME/llamasystem.org/mdr/moreau" "$HOME/llamasystem.org/mdr/moreau-test-$(date +%Y%m%d-%H%M%S)"
cd ~/mdr_race_tracker
sh deploy/dreamhost-publish.sh
```

Check **https://www.llamasystem.org/mdr/moreau/**. Confirm:

- The heading says **Moreau Half 2026**, without the fictional-test badge.
- The roster count matches the import; names and bibs are the actual field.
- The configured start is correct; the clock is zero before the start.
- The source connects successfully and no fictional reports appear.

Do not add invented passages to the real race Doc just to test movement. Use the
separate fictional test for that. The real page can be verified with an empty Doc.

## 9. Resume once-per-minute publishing

Run `crontab -e` again and remove the leading `#` from the tracker job:

```cron
* * * * * /bin/sh /home/dh_6n4gzz/mdr_race_tracker/deploy/dreamhost-publish.sh >> /home/dh_6n4gzz/mdr-tracker-data/publish.log 2>&1
```

Save, then check:

```sh
crontab -l
tail -n 10 ~/mdr-tracker-data/publish.log
```

Cron now uses the real config/roster/Doc. The browser automatically loads updates
after publication; runner positions remain at last confirmed checkpoints.

## Late registrations and bib changes

For the simplest race-day workflow, enter `ADD bib | Full Name` in the separate
[RD command log](DIRECTOR-LOG.md), then tell net control and timing/check-in staff.
The next publish adds that runner and rechecks pending radio messages. Use
`DNS bib` and `UNDO DNS bib` there for start-list decisions. RD additions persist
in the race database, independently of the exported roster file.

If Google access is unavailable, run `python3 -m tracker.add_runner` on DreamHost;
it prompts for bib/name and updates the existing roster file. File changes load on
the next publish. Do not reuse an assigned bib for another runner.


Export UltraSignup again on the Mac, rerun the same local import, then repeat the
JSON upload/rename commands in step 3. Do not upload the full export.
For new runners, check the new count; the next cron run loads them automatically.
Imports preserve existing runners absent from a later export; removals require review.
Local imports are atomic and retain a `.bak` of the prior local roster.
If you used the hosting-shell add-runner fallback, bring that updated host roster
back to the Mac before a later upload, so file-only additions are preserved.
RD-log additions live in the database and are unaffected by roster-file uploads.

Once reports have been recorded, do not remove their runners from the roster or
reassign their bibs: the history is keyed by bib. If the import detects a changed
name for an existing bib, it stops for review. A corrected assignment or removal
after the race has started needs a deliberate data review, not a blind overwrite.

## Troubleshooting and rollback

- **No new passages:** check the private publish log, Doc access, report syntax,
  actual bibs, and the page's last successful source read.
- **Import says no assigned bibs:** assign bibs in UltraSignup and export again.
- **Output belongs to another race:** the old test page has not been moved aside.
- **Need to return to the test:** pause cron, restore `~/.mdr-tracker-test.env.backup`
  to `~/.mdr-tracker.env`, rename the current real output folder to a new backup
  name, and run the publisher. Keep both databases. Resume cron only after review.
- **Viewing the private operator audit:** use the continuous local test server;
  public static files intentionally do not contain the raw log or review details.

The password remains in 1Password. Google tokens, registration exports, local
config/roster and SQLite databases remain outside Git; raw exports and databases
also stay outside the public website directory.


## Radio operators' existing table

The tracker now reads the existing TIME / MESSAGE format automatically, including
HHMM times, groups of bibs, embedded passage times, finishes and drops. The radio
operators do not need to type ID/pipe lines. Keep the original radio log as the
source of record. The real Moreau document is:

https://docs.google.com/document/d/1tP6AB0TFm3xSzfCjAdRv9Tek6zcI7-6_vIaPBeKtSaA/edit

Once the real roster, confirmed start and separate race database are ready, set
`TRACKER_GOOGLE_DOC` in `~/.mdr-tracker.env` to that URL and publish normally.
Do not point the fictional test configuration at real race traffic.

Ambiguous messages remain in private review. On DreamHost, read the cron log's
review counts and inspect input issues with the actual `TRACKER_DATABASE` path:

```sh
cd ~/mdr_race_tracker
python3 -m tracker.review --database ~/mdr-tracker-data/moreau-test.sqlite3
```

Replace the test database path above with the race-day database when switching.
The local staff view also checks backwards progress and reports after withdrawal
or finish. A separate prose correction is flagged for review; after checking it,
the director can edit the original table row. The spectator site contains no raw
radio messages or review details.
