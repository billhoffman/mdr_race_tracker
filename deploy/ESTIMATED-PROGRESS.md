# Estimated progress display

The map defaults to **Estimated progress**, with a **Confirmed checkpoints** button
for the original view. No extra environment setting is needed. Push/pull the code
and run the normal DreamHost publisher once; refresh the page for the new assets.

- Solid numbered circles remain at each runner's last individually confirmed
  checkpoint. Table statuses, finish places, counts and recorded passages retain
  their existing meanings.
- Smaller dots move along the supplied course using computed pace. Selecting a
  dot or runner shows the estimate and the last confirmed checkpoint/time.
- Dots fade from green toward amber as time since the last real observation grows.
  A dashed outline indicates progress inferred from an all-runners-passed report.
- The same estimated dots appear on the elevation profile.
- Only known on-course runners get estimates. RD `START ALL` / `START bib`
  confirms participation and allows start-based estimates without invented passages.
  Registrations without a passage or start declaration,
  DNS runners, withdrawals and finishers do not get animated estimates.

## Pace and limits

A runner with two distinct confirmed checkpoint passages gets a pace estimate
from the median of their last three plausible segment speeds. Until then, the
model uses median observed field pace, including start-to-first-checkpoint samples.
When no pace samples exist, it uses a labelled fallback of 1.25 meters/second.
This initial model uses course distance, not an elevation-adjusted effort model.
Aid-station stops, climbs and changes in effort can make estimates inaccurate.

Between observations a dot moves toward the next checkpoint, stopping five percent
short until passage is confirmed or aggregate evidence supplies a later inference
boundary. It never invents a finish, withdrawal, runner place or GPS fix. The
normal browser timer updates estimates between minute-by-minute publications.
Only the live race clock extrapolates time; the fictional report clock stays at
its latest report for repeatable rehearsal.

## Aggregate radio reports

Existing natural radio messages are read automatically:

```text
Checkpoint G All runners passed and sweep has passed. Cleared to secure
```

This exact message was reported at 11:01 in the Buck 50 log. It supplies a separate
display-only boundary. A known on-course runner with an older, earlier individual
report can be inferred beyond G. Their recorded checkpoint and report history do
not change. The inferred position is labelled/dashed and has reduced confidence.
A newer individual report behind G takes precedence over an older aggregate report.

A last-runner report alone, a sweep team's passage, or Garmin GPS does not clear
all runners. Counts, "all but two", questions, gender-specific leaders and
ambiguous/correction messages do not establish a whole-field boundary. Anonymous
first-runner reports are stored separately from bib-specific passages, and their
timestamps do not justify an estimate beyond that checkpoint before it happened.
No bib identity or overall place is inferred from them.

A boundary under an invalid edit or removed from the document is held from the
estimate view while its original remains in the audit. The radio staff do not
need to operate the tracker or change their workflow. Explicit checkpoint/bib/time
reports remain the best source of individual progress.

## Rehearse locally

From the checkout on your Mac:

```sh
python3 -m tracker.server --source file --log races/moreau-test/progress-radio-log.txt --database outputs/tracker/progress-demo.sqlite3
```

Open http://localhost:8000. The six fictional runners show a mixture of individually
estimated and aggregate-inferred positions. Toggle Confirmed checkpoints and select
runners to compare. The test clock freezes at its latest report; the real race's
live clock moves estimates automatically. Use a separate port/database if another
local test is already running. Keep rehearsal reports out of the actual Google Docs.

## Recording and replay

The private audit and export retain aggregate reports separately from individual
observations. Estimated coordinates are computed in the browser and are not stored
as measured GPS or confirmed runner passages. The pure `tracker/web/progress.js`
module can also be used by a later replay renderer with the archived source data.
The sweeper broom remains tied to actual Garmin GPS fixes.

## Sharing with spectators

The map offers an Estimated progress view as well as Confirmed checkpoints.
Small dots are approximate, pace-based positions; solid numbered circles show
runners' last reported checkpoints. Estimates pause before unconfirmed checkpoints
and fade as uncertainty increases. They are not live GPS positions.
