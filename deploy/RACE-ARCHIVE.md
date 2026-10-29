# Race data capture and post-race replay export

The private SQLite database is the race record, separate from the website files:

```text
/home/dh_6n4gzz/mdr-tracker-data/moreau-2026.sqlite3
```

Use the actual `TRACKER_DATABASE` path if your environment differs. The current
publisher saves the following automatically, without additional cron jobs:

- Accepted runner observations and every correction/void, with original text,
  event time, time basis and when the tracker received the observation.
- Accepted director commands: additions/removals, DNS decisions, start corrections
  and passage/finish/withdrawal overrides, retained with their audit history.
- Each changed version of the radio and director input as read by the tracker,
  including incomplete messages, deleted rows and commented instructions.
- Each changed base configuration, including course coordinates/elevations,
  checkpoints, roster, race date/timezone and configured start time.
- Every distinct valid race-day Garmin GPS fix returned in a successful feed read,
  not just the latest position. Older fixes returned later are also saved.
- Successful and failed source reads, with timestamps, for identifying outages.

The active record and histories survive cron runs and code updates. Repeated reads
of unchanged inputs do not add full duplicate copies. GPS history records report
time and first receipt time separately. The course/config snapshots preserve the
geometry and local elevation backfill used during the race.

Deploy this archive support before race day. Runner/RD revisions were already
saved by earlier versions. Full input snapshots and continuous GPS history begin
with this update; a previously saved latest GPS position can be recovered, but
older unrecorded positions cannot be manufactured. Later Garmin reads can fill
those gaps only if the feed still returns the missing reports.

Snapshots reflect the polling interval: an edit created and erased between polls
is not recoverable. Garmin message text, device identifiers and unrelated-day GPS
are not collected. Raw radio/RD versions and race-day GPS stay private, outside
the spectator site. Only the current public status is published.

## Export on DreamHost

After pulling the new code, the next publication creates the archive tables in the
existing database automatically. There is no need to reset or replace the database.

After the race, create a portable archive:

```sh
cd ~/mdr_race_tracker
python3 -m tracker.export_race \
  --database "$HOME/mdr-tracker-data/moreau-2026.sqlite3" \
  --output "$HOME/mdr-tracker-data/moreau-2026-replay.zip"
```

The command uses SQLite's backup facility to make a consistent copy even if cron
is still running. The ZIP contains `race.sqlite3`, readable JSONL files for the
histories and a manifest with counts and capture dates. It never overwrites an
existing export: use a different filename for later copies. Keep the archive in
the private data directory.

Download it from your Mac:

```sh
scp dh_6n4gzz@pdx1-shared-a1-19.dreamhost.com:mdr-tracker-data/moreau-2026-replay.zip "$HOME/Downloads/"
```

Keep the downloaded ZIP and the original race database. Moving/rebuilding the
public `mdr/moreau` website does not affect the private database.

## Movie use

A separate movie renderer can read this export to build the post-race simulation,
using the final corrected start and observed checkpoint/finish times. It can also
reconstruct what information was known at each receipt time. The sweepers have an
actual GPS trail; runners still have checkpoint observations, with simulated
movement between them. Official finalized results and selected photographs can
be incorporated separately in the movie workflow. The live tracker and archive
export do not depend on the movie renderer or DEC-report tools.
