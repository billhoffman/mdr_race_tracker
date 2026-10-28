#!/bin/sh
# Short, one-shot job. No background process or listening port is started.
set -eu
ENV_FILE="${TRACKER_ENV_FILE:-$HOME/.mdr-tracker.env}"
if [ ! -r "$ENV_FILE" ]; then
    echo "Create $ENV_FILE from deploy/dreamhost.env.example first." >&2
    exit 1
fi
. "$ENV_FILE"
: "${TRACKER_GOOGLE_DOC:?Set TRACKER_GOOGLE_DOC in the environment file}"
: "${TRACKER_WEB_ROOT:?Set TRACKER_WEB_ROOT to the dedicated public tracker folder}"
TRACKER_REPO="${TRACKER_REPO:-$HOME/mdr_race_tracker}"
TRACKER_DATABASE="${TRACKER_DATABASE:-$HOME/mdr-tracker-data/moreau-test.sqlite3}"
TRACKER_PYTHON="${TRACKER_PYTHON:-/usr/bin/python3}"
cd "$TRACKER_REPO"
set -- --source google --google-doc "$TRACKER_GOOGLE_DOC" \
    --database "$TRACKER_DATABASE" --web-root "$TRACKER_WEB_ROOT" --expected-interval 60
if [ -n "${TRACKER_CONFIG:-}" ]; then set -- "$@" --config "$TRACKER_CONFIG"; fi
if [ -n "${TRACKER_ROSTER:-}" ]; then set -- "$@" --roster "$TRACKER_ROSTER"; fi
if [ -n "${TRACKER_GOOGLE_TOKEN:-}" ]; then set -- "$@" --google-token "$TRACKER_GOOGLE_TOKEN"; fi
exec "$TRACKER_PYTHON" -m tracker.publish "$@"
