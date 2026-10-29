# Sweeper GPS tracking

The tracker can read the public Garmin MapShare link:

https://share.garmin.com/4YNCH

Its KML feed was verified at:

https://share.garmin.com/Feed/Share/4YNCH

The map shows a broom at the last reported GPS coordinate. It moves when a new
report is received; it does not extrapolate the sweep team's movement between
fixes. The status line shows the fix's clock time and age. After 30 minutes the
broom fades and the status identifies the position as potentially outdated.

## Enable on DreamHost

After pushing the code from the Mac and pulling it on DreamHost, add this to the
existing `~/.mdr-tracker.env`:

```sh
TRACKER_SWEEPER_URL="https://share.garmin.com/4YNCH"
```

Then publish normally:

```sh
cd ~/mdr_race_tracker
git pull --ff-only
sh deploy/dreamhost-publish.sh
```

The same one-minute cron job reads Garmin as well as the radio and director Docs.
No additional process, cron job or hardware is needed for the website. The inReach
must have tracking and public MapShare sharing enabled and send GPS reports.
Polling the website each minute does not change the device's reporting interval.

Before October 31, the page will show **Waiting for a race-day GPS report near the
course**. The broom appears only for the configured race date and near the course.
A report more than 500 meters from the route is labelled outside the course area;
its coordinates are omitted from the spectator snapshot. Yesterday's position
will not appear as today's sweep team.

The actual GPS coordinate is used on the map, not a position snapped to the route.
Approximate course miles are calculated from the nearest route segment. Where
nearby segments represent very different course distances (e.g. start/finish or
crossings), the distance is marked uncertain and no elevation-profile broom is
shown. Otherwise a smaller broom also appears on the course elevation profile.

Garmin tracking is independent of runner observations and never changes runner
counts, DNS decisions or checkpoints. If Garmin is unavailable, radio/director
processing continues and the last GPS fix is retained with an error/age notice.
The position survives cron runs and restarts. Every distinct race-day fix returned
by Garmin is also saved privately for the [post-race replay export](RACE-ARCHIVE.md),
including older fixes received later. Removing the environment setting
hides the broom again. Raw messages, device identifiers and raw KML are not
published or committed to Git.

## Local options and tests

The local server and publisher accept `--sweeper-url URL`. For offline tests use
`--sweeper-kml PATH` with a KML fixture; the same race-date/location checks apply.
A different feed/date does not inherit the old source's cached GPS position.
Use a separate test database and fictional data for a rehearsal.

```sh
python3 -m unittest tracker.tests.test_sweepers -v
node --test tracker/tests/test_sweepers.cjs
```

Tests cover the KML reader, GPS time/fix validation, race-date filtering, approximate
course distance, ambiguous crossings, source failures, retained positions,
private-field exclusion, independent radio/RD processing and stale-marker labels.
