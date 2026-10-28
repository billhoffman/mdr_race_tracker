# Moreau local test: reports to type into your Google Doc

The six runners and 09:00 start are fictional. These are test times, not the real
Moreau schedule. The tracker clock follows the newest observation, so you can type
these reports at any time of day. Allow 15-20 seconds after each step for the next
Google Doc read. Copy only the report lines, not this document's prose/headings.

Use one paragraph per report. Keep earlier lines in the document.

## 1. Start all six runners

```text
T000 | 09:00 | START | 101,102,103,104,105,106 | PASS
```

Expected: six on course; all six markers at the start; race clock 00:00:00.

## 2. First runners at A

```text
T001 | 09:10 | A | 101 | PASS
T002 | 09:12 | A | 102,103 | PASS
```

Expected: three at A, three last confirmed at start; race clock 00:12:00.

## 3. Two more reports, including one late arrival

```text
T003 | 09:35 | B | 101 | PASS
T004 | 09:18 | A | 104 | PASS
```

Expected: 104 is at A with an actual passage time of 09:18, even though entered
after 09:35 was reported. Race clock stays at 00:35:00.

## 4. Withdrawal and more passages

```text
T005 | 09:38 | A | 102 | WITHDRAWN
T006 | 09:40 | B | 103 | PASS
T007 | 09:22 | A | 105,106 | PASS
```

Expected: one withdrawn, five on course. Do not infer a runner's present position
between checkpoints.

## 5. Correct an existing report

Change the ORIGINAL T003 line (do not add another T003):

```text
T003 | 09:34 | B | 101 | PASS
```

Expected: bib 101's B passage changes from 09:35 to 09:34. The audit history keeps
both revisions; the runner is not duplicated. Clock remains at 00:40:00.

## 6. Check validation

```text
T008 | 09:50 | C | 999 | PASS
```

Expected: unknown bib 999 appears under Reports needing attention. No runner moves.
Then edit that SAME line:

```text
T008 | 09:50 | C | 101 | PASS
```

Expected: issue clears; bib 101 moves to C.

## 7. Aid stations and later course progress

```text
T009 | 10:15 | D | 101,103 | PASS
T010 | 10:30 | D | 104,105,106 | PASS
T011 | 10:45 | E | 101,103 | PASS
T012 | 11:05 | F | 101,103 | PASS
T013 | 11:25 | G | 101,103 | PASS
T014 | 11:40 | H | 101 | PASS
```

Expected: D and G are aid stations; movement follows reports only. Skipped
intermediate reports are permitted; an impossible backwards report is flagged.

## 8. First finish, then a retraction

```text
T015 | 11:55 | FINISH | 101 | FINISH
```

Expected: bib 101 is provisional first finisher with elapsed 02:55:00.
To test retraction, replace the entire T015 line with:

```text
T015 | VOID
```

Expected: 101 returns to their previous last confirmed checkpoint H. Replace the
VOID line with the original finish line to restore it:

```text
T015 | 11:55 | FINISH | 101 | FINISH
```

Both changes are retained in the audit log.
Simply deleting an accepted line does NOT retract it: use VOID.

## 9. Complete the test

```text
T016 | 12:05 | H | 103 | PASS
T017 | 12:15 | FINISH | 103 | FINISH
T018 | 12:30 | G | 104,105,106 | PASS
T019 | 12:50 | H | 104,105,106 | PASS
T020 | 13:10 | FINISH | 104 | FINISH
T021 | 13:15 | FINISH | 105 | FINISH
T022 | 13:20 | FINISH | 106 | FINISH
```

Expected: five finished, one withdrawn; race clock 04:20:00. Restarting the server
with the same database preserves the observations without duplicating them.

## Connectivity test

Temporarily disconnect the input or change the sharing permission. The page should
show a source error while retaining confirmed race data. Restore access and the next
successful poll should resume updates. Do not delete the Google Doc or your database.
