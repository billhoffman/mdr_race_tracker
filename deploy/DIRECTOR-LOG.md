# Race director log

The tracker reads this document independently of the radio team's TIME/MESSAGE log:

https://docs.google.com/document/d/1wUvZ85JdPXbxxoOp-JBgTGqv2LypBgUackv9q7ktpK4/edit

Give the tracker viewer access and race staff editing access. The application only
reads the document. It does not write instructions or reports into either Doc.

## Commands

Type one command per paragraph, using actual assigned bibs and actual local clock
times. These are examples: do not enter fictional observations in the real log.

| Action | Example |
|---|---|
| Add a late entrant | `ADD 118 \| Jane Smith` |
| Mark did not start | `DNS 42` |
| Reverse an incorrect DNS | `UNDO DNS 42` |
| Record/correct a passage | `PASS 118 \| G \| 11:25` |
| Record/correct a finish | `FINISH 118 \| 13:42:10` |
| Record a withdrawal, location unknown | `WITHDRAW 118 \| 11:30` |
| Record a withdrawal at a known station | `WITHDRAW 118 \| G \| 11:30` |
| Remove a director passage override | `UNDO PASS 118 \| G` |
| Remove a director finish override | `UNDO FINISH 118` |
| Remove a director withdrawal override | `UNDO WITHDRAW 118` |

Times are time of day on the configured race date, in the configured timezone
(America/New_York for Moreau). They are not elapsed race time. HHMM, HH:MM and
HH:MM:SS are supported. The displayed race clock remains elapsed time.

Put ADD above commands for a new runner. The addition stores only bib/name in the
private race database and remains available after cron/server restarts and roster
re-imports. It does not alter UltraSignup or the radio team's document. Tell net
control and the timing/check-in staff the same bib/name. Reassigning an existing bib
to a different name is rejected.

Use the document as a running log: **append commands**. No entry IDs are needed.
Accepted commands are applied once and survive temporary failures. Deleting or
editing an accepted command does not undo its prior effect. Append UNDO commands
or a correcting PASS/FINISH/WITHDRAW instead. A deleted accepted line raises a
private review notice. Lines beginning with `#` are comments and are ignored.

DNS has its own count and status. It is different from Not reported and Withdrawn.
UNDO DNS restores status from the runner's confirmed observations. DNS takes
precedence over observations until undone; a conflicting radio report is flagged.

The latest accepted director passage for a bib/checkpoint supersedes radio
observations for that same bib/checkpoint. The latest director FINISH/WITHDRAW
supersedes radio terminal reports for that bib. UNDO restores the radio-based
behavior for that override; it does not undo a radio withdrawal or radio finish.
Other checkpoint reports remain subject to progression validation. Conflicts stay
in the private review/audit; the source records are retained.

## Enable on DreamHost

After the updated code has been pushed and pulled on DreamHost, edit the existing
`~/.mdr-tracker.env` and add:

```sh
TRACKER_DIRECTOR_DOC="https://docs.google.com/document/d/1wUvZ85JdPXbxxoOp-JBgTGqv2LypBgUackv9q7ktpK4/edit"
```

Keep `TRACKER_GOOGLE_DOC` pointing at the radio log. Keep the configured real
roster/start/database; adding this setting does not switch a fictional test to
the real race. Follow the [race-day runbook](MOREAU-RACE-DAY.md) for that switch.

Publish once, then the same one-minute cron job reads both:

```sh
cd ~/mdr_race_tracker
sh deploy/dreamhost-publish.sh
```

The page reports radio and RD source health separately. If one read fails, the
other source can continue and the failed source's last confirmed data is retained.
The private review command includes invalid commands and progression conflicts:

```sh
python3 -m tracker.review --database ~/mdr-tracker-data/moreau-2026.sqlite3
```

Use the database path actually configured in your environment file. The public
page shows runner names/status/progress, with no raw commands or private review.

## Offline rehearsal

Run this on your Mac from the Git checkout. It uses six fictional runners plus one
fictional late entrant and a separate database:

```sh
python3 -m tracker.server --source file --log races/moreau-test/radio-log.txt --director-log races/moreau-test/director-log.txt --database outputs/tracker/director-test.sqlite3
```

Open http://localhost:8000. Edit the local director file and save to try commands;
leave the real Google Docs free of practice reports. The server reads the two
files each polling cycle. The automated director tests also cover a pending radio
report being released after an ADD command, restarts, DNS reversal, corrected
finishes, repeated commands and independent source failures:

```sh
python3 -m unittest tracker.tests.test_director tracker.tests.test_buck50 -v
```
