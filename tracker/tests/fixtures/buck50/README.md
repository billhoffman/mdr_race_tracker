# Buck 50 radio regression fixture

`radio-log.html` preserves the tables from the supplied
`10.3.2026 - Buck 50k Race Log.docx` (October 3, 2026). It was converted once using
Python's ZIP/XML reader, retaining cell and paragraph boundaries, including blank
rows and multiline messages. The 290 populated TIME rows are the actual radio
messages; spelling, ambiguous bibs, clock discrepancies and prose corrections are
retained. The table has no added test reports or parser-specific IDs.

`expected.json` contains 47 bibs, manually checked expected radio outcomes and
selected passage times. Runner names, registration/contact data and official
finish times are excluded. Placeholder names are created only inside the test.
The first course distances and route length come from the supplied Buck track.

Run from the repository root, without internet or the original DOCX:

```sh
python3 -m unittest tracker.tests.test_buck50 -v
```

These tests are also included automatically in the normal command:

```sh
python3 -m unittest discover -s tracker/tests -v
```

The regression checks:

- The production HTML reader, polling pipeline and SQLite ingestion accept the
  original table: 222 individual provisional observations, all 42 radio-recorded finish bibs,
  and withdrawals 16, 28, 29 and 55.
- Embedded passage times, grouped bibs, paragraphs within a cell, mixed drops and
  passages, and the finish lines with unmarked bibs retain their intended meaning.
- Bib 47 has no invented radio finish. Its official finish was supplied separately
  in the historical movie; the live parser never reads those results.
- Unknown bibs 1/87, duplicate bib 31, prose corrections and outstanding-runner
  messages are held for review. Sweep numbers do not become runner bibs.
- Replaying rows as the document grows, reading it repeatedly and restarting the
  database produce no duplicate revisions or future finish observations.
- Editing a real grouped report replaces the group and keeps its audit history.

This tests radio ingestion and the final confirmed status summary. It does not
validate the historical movie, official timing, or Buck's complete position history.
The current live tracker models one visit per checkpoint; Buck revisits A/B/C/D.
The test deliberately retains progression warnings from its return leg, rather
than hiding them with made-up checkpoint visits. Moreau uses a single visit per
checkpoint. A future repeated-visit model should add separate course tests here.

The drop for bib 29 is recognized in the explicit 15:52 report. The earlier 15:50
entry is phrased as a question and is held for review; the test does not silently
substitute the retrospective director-confirmed drop time.

The original 11:01 checkpoint G "All runners passed and sweep has passed" row is
also tested as a separate display-only clearance boundary. Last-runner reports
at H, I and J do not clear the whole field. Aggregate records add audit revisions
but do not add bib-specific observations or change the expected finish/drop counts.
