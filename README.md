# WhatsApp Quiz Studio for macOS

A local quiz host for WhatsApp Desktop: explicit aliases, chronological first answers, transparent rank-based points and private JSON storage. There is **no LLM, WhatsApp Web or cloud service**. Application data stays in JSON. Incoming messages are read from WhatsApp Desktop’s existing local SQLite database through read-only connections; readable sender names are resolved from the adjacent native ContactsV2.sqlite when available. The bot never writes to either database.

The application includes a French local dashboard with editable game settings, Start/Stop controls, automatic participant names and a live leaderboard, plus a question editor, an answer tester, a deterministic simulator, direct native message reading, an accessibility sender, durable game snapshots and explicit incident recovery. **Validated native gameplay is gated by a controlled transport test; a separate, explicit real-rehearsal mode is available for testing.** Direct reading has recovered 100 local records without scrolling, preserving their authors, timestamps and native sequence. That diagnostic does not replace a controlled question/STOP test.

## Requirements and limitations

- **macOS only**, on a Mac laptop or desktop. Python 3.12 is recommended; PyObjC supplies the native APIs. See [PyObjC supported platforms](https://pyobjc.readthedocs.io/en/latest/supported-platforms.html).
- WhatsApp Desktop must be installed and signed in, and the macOS session unlocked. Native game commands launch WhatsApp if it is closed, reopen its window when necessary, wait for accessibility readiness, then automatically search for the configured group, select only an exact unique conversation-name match and verify the active header. Missing or ambiguous matches abort before publication. Existing message drafts are preserved and prevent sending. Read-only accessibility diagnostics still require the intended group to be visible.
- Keep WhatsApp available while a native game is running. Avoid navigating to another chat or changing the desktop during collection. Players may send media or delete messages without interrupting gameplay.
- WhatsApp’s internal database schema and accessibility selectors are undocumented and version-dependent. Missing boundary identities, invalid text-message identity metadata or ambiguous native ordering pause a game instead of producing a partial leaderboard. Media, system events and deleted-message placeholders are filtered before sender, timestamp and order validation.
- Reading covers **locally synchronized records**, not the full cloud history. A fresh read transaction includes the live database journal. Missing or unavailable local data blocks collection; no completeness claim is made about unsynchronized messages.
- Native sender identities are hashed before application storage. Names come from scoped queries in the native contact database, with group-member labels or a neutral identity suffix as fallback; encoded push metadata is never displayed as a name. Two participants sharing a display name remain separate players, with short identity suffixes in results. Missing sender identities for answers or registrations block scoring. Names are not verified real-world identities.
- The message database supplies native timestamps with seconds and a conversation sequence. Eligibility and rank use the strict native sequence between the confirmed outgoing question and STOP message identities, rather than clock comparisons or display order.
- The current implementation was checked on macOS 26.6.2, Python 3.12 and PyObjC 12.2.2. Other supported combinations require their own native validation.
- This service does not automatically resume after a crash, logout or shutdown. Timers work only while the local process is running. Recovery always requires an operator action.

## Install and start

From the project directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
mkdir -p data
cp questions.example.json data/questions.json
python -m quiz_app
```

Open **http://127.0.0.1:8765**. The server binds only to loopback and uses one worker. A process lock prevents multiple services sharing the same private data directory. Do not expose it through a proxy or bind it to a public interface.

The dashboard loads its defaults from `.env`. Edit them in **Préparer la partie**, select questions, choose a mode and click **Démarrer**. There is no need to supply terminal parameters for each game. **Enregistrer dans le .env** saves the defaults atomically to the private file; **Démarrer** uses the current form values even if you have not saved them. Every new game snapshots its settings and selected questions; changing the bank or defaults never changes a running game. Advanced options include commands, polling, native database path and server port. A port change takes effect only after restarting the server.

Choose one of three explicit modes:

- **WhatsApp · partie de test réelle** launches WhatsApp if necessary, finds the configured group and publishes a real rehearsal. This mode does not create a transport-validation receipt.
- **WhatsApp · transport validé** requires a matching private controlled-test receipt before publishing.
- **Simulation locale · aucun envoi** runs entirely locally and reveals the simulated-player controls.

The live view shows automatically discovered participant names, the active question, remaining time and accumulated scores. It refreshes once per second; collection uses the snapshotted `POLL_SECONDS`. Open-round points are clearly labeled **PROVISOIRE** and become confirmed only after STOP and complete segment verification. An incomplete or ambiguous collection pauses the game and never becomes a confirmed ranking.

After each round's answer and intermediate ranking, the same message announces how many seconds remain before the next question, using `INTERVAL_SECONDS`. The interval starts after the result announcement is confirmed. A zero interval announces an immediate next question; the last round does not announce another question.

Use **Arrêter** in the fixed header or beside **Démarrer** to cancel at any stage, including native startup. The request is signaled immediately while a native operation finishes; it prevents subsequent sends and ends the game locally without an extra WhatsApp announcement. A message already being published cannot be recalled. Cancelled and finished games do not continue polling WhatsApp or rewriting their archives.

| Variable | Example | Meaning |
|---|---:|---|
| `WHATSAPP_GROUP` | `Test` | Exact native group name (automatically searched at startup) |
| `MAX_PLAYERS` | 20 | Registration limit; enrolled count freezes at closure |
| `NB_PLAYERS_EXPECTED` | 1 | Minimum enrollment at closure; fewer players cancels the game |
| `MAX_QUESTIONS` | 30 | Maximum questions per game |
| `REGISTRATION_SECONDS` | 60 | Registration window |
| `QUESTION_SECONDS` | 30 | Answer window before publishing STOP |
| `INTERVAL_SECONDS` | 10 | Delay after round results |
| `POLL_SECONDS` | 1 | Engine polling delay |
| `JOIN_COMMAND` | `!join` | Case-insensitive enrollment command |
| `ANSWER_PREFIX` | `!r` | Case-insensitive answer command |
| `IGNORE_ACCENTS` | true | Optional accent removal |
| `MAX_POINTS`, `MIN_POINTS` | 100, 20 | Correct-answer scoring endpoints |
| `MAX_HISTORY_PAGES` | 1000 | Traversal budget for the legacy accessibility diagnostic only |
| `WHATSAPP_DATABASE` | Default WhatsApp group-container path | Existing local database; opened read-only |
| `MESSAGE_CHUNK_SIZE` | 3000 | Maximum visible outgoing message size |
| `PORT` | 8765 | Local HTTP port |

Use double quotes around text values. Invalid fields, duplicate keys, conflicting commands and inverted point limits fail validation explicitly.

## Questions and correction

The JSON editor accepts a nonempty array with unique stable IDs:

```json
[
  {
    "id": "capital",
    "question": "What is the capital of France?",
    "answer": "Paris",
    "aliases": ["Ville de Paris"],
    "explanation": "Paris is the capital of France."
  }
]
```

Save, import or export the bank from the dashboard. Under **Gérer la banque de questions**, select a question and choose its correction mode. Click **Appliquer au brouillon JSON**, then **Enregistrer les questions** to use it in future games. The tester uses the selected draft question, its displayed correction options and the form's accent setting, including unsaved changes. It shows the matching official answer or alias and the reason for acceptance or rejection. Saving a bank never changes a running game's frozen rules or previously awarded points.

Correction normalizes Unicode, letter case, whitespace and curly apostrophes. Accent removal is optional. Common terminal punctuation is removed, while `C++`, `C#` and `-5` remain significant. There is no fuzzy spelling correction or inferred semantic similarity. Choose one explicit `grading_mode` per question:

| Mode | Rule | Example |
| --- | --- | --- |
| `exact` (default) | Complete equality with the answer or a declared alias after normalization | `PARIS!` matches `Paris`; `Paris France` does not |
| `person_name` | Exactly the same words as a full answer or alias, including repeated words, in any order | `Potter Harry` matches `Harry Potter`; `Harry`, `Harry Harry Potter` and `pas Harry Potter` do not |
| `number` | Exact decimal equality with a reference and an allowed unit, with no numeric tolerance | `12,00 km` matches `12 km` if `km` is declared |

Old questions without `grading_mode` remain `exact`. Set `person_name` only for names of people or characters; it does not infer that a surname alone is sufficient. Add a short name explicitly to `aliases` if you want to accept it. Internal apostrophes and hyphens remain significant, and words cannot be added or dropped. Typos, incomplete answers, negations and multiple alternatives remain rejected unless the complete submitted form is an explicitly declared alias.

For `number`, use `units` to list equivalent spellings of the expected unit, and `require_unit` to require one. Empty `units` accepts only bare numbers. When units are declared but not required, both bare values and values with a declared unit are accepted. Official answers and aliases must also be valid numeric forms respecting this rule. The validator rejects conflicting settings and malformed references:

```json
[
  {
    "id": "wizard",
    "question": "Which character attends Hogwarts and has a lightning-shaped scar?",
    "answer": "Harry Potter",
    "grading_mode": "person_name",
    "aliases": []
  },
  {
    "id": "distance",
    "question": "What is the distance in kilometres?",
    "answer": "12 km",
    "grading_mode": "number",
    "units": ["km", "kilomètres"],
    "require_unit": true,
    "aliases": []
  }
]
```

Numbers use Python `Decimal`, preserving exact precision rather than rounding floats. A comma or dot denotes the decimal separator (`1,200` means `1.2`). Signs and leading zeroes are accepted. There are no thousands separators, scientific notation, fractions, expressions, unit conversions or conversion of written-out numbers. Keep `exact` with explicit aliases for forms such as `twelve`. Unit labels express the same unit, so never declare both `km` and `m` for the same value. Per-answer matching reasons are stored in session results and available in the editor; they are not added to player announcements.

## Rehearse without sending anything

1. Choose **Simulation locale · aucun envoi**, select questions and click **Démarrer**; all bank questions are initially selected, up to the configured limit.
2. Submit `!join` with fictional player names from **Simuler un joueur**.
3. When enrollment closes, submit `!r Paris` for the active question. No question number is needed.
4. Watch the STOP, results, next question and final scoreboard in the stored session evidence.

Simulation never opens or publishes to WhatsApp. Use shorter local durations if desired. Only the first nonempty command-form answer from each registered player counts. Answers between STOP and the next question are ignored. A reply after the next question belongs to that new round.

## Permissions and native diagnostics

In **System Settings → Privacy & Security → Accessibility**, enable the terminal used for manual commands and the actual Python executable used to start the service. macOS grants can differ between the terminal and a background launcher.

Find the real executable:

```sh
.venv/bin/python -c 'import os, sys; print(os.path.realpath(sys.executable))'
```

Click **+**, then **Cmd+Shift+G** and paste that path. If the picker hides the executable, select it in Finder and drag it into the Accessibility list; enable its switch. Restart the terminal/service after granting access if needed. See [Apple Accessibility settings](https://support.apple.com/en-gb/guide/mac-help/mchl211c911f/27/mac/27).

Database reading also requires macOS to permit access to the configured WhatsApp group-container file. Accessibility permission does not itself grant file access. If reading reports `SOURCE_UNAVAILABLE`, check the path and operating-system denial first. Grant Full Disk Access to the actual launching terminal or Python only if macOS denies these sources; use **Privacy & Security → Full Disk Access** and the same executable-selection procedure. Do not copy the live database or its journal into Git.

Read the latest 100 local text records **without scrolling or sending** (media, system events and deletion notices are skipped):

```sh
python -m scripts.read_messages --group "Test" --count 100
# Optional private export, including authors, UTC timestamps and exact bodies:
python -m scripts.read_messages --group "Test" --count 100 --output data/diagnostics/test.json
```

The count includes records without a text body. The command reports how many records actually exist locally; it does not invent missing history. Complete quiz-window reads have no viewport limit and are scoped to one exact group.

The older accessibility prototype remains available as a **read-only diagnostic**, not the production history reader:

```sh
python -m scripts.probe_whatsapp --group "Test"
```

It prints row counts and order/overlap diagnostics, without printing message contents, saving them or sending messages. Permission denial is explicit. A failed overlap is a failure to establish continuity, even if the visible rows individually look correct.

### Controlled test, prepared for later

Do not enable real play on the strength of unit tests or a viewport inspection alone. Arrange at least three known incoming replies from another account, in a known order. Use distinct participant labels for this human-readable validation fixture. Store the expected transcript privately in `data/expected.json`, for example:

```json
[
  {"author": "Camille", "body": "!r Paris"},
  {"author": "Camille", "body": "!r Londres"},
  {"author": "Robin", "body": "!r Paris"}
]
```

These are fictional labels; replace them with the actual test accounts and agreed responses. **The following command sends a question boundary and STOP in Test:**

```sh
python -m scripts.validate_transport --expected data/expected.json --seconds 30
```

Stop the web service before this command: the validator acquires the same exclusive service lock. The validator opens Test automatically; ensure its message composer is empty. Send the agreed replies during the announced window. The test compares the complete recovered segment with the exact expected authors, bodies and order. Success writes a private validation receipt. Only then does the dashboard accept **WhatsApp · transport validé** for the matching group. Explicit real rehearsals remain a separate testing mode and do not establish validation.

Each validation send is reserved in a private diagnostic JSON before publication. A missed or uncertain send is never silently retried. Inspect WhatsApp and that reserved message first; the validator does not automatically recover or replay an interrupted attempt. This test is currently restricted to Test; adapting and validating another target group is a separate explicit operator step.

All player announcements are in French, with WhatsApp's native `*bold*` and `_italic_` syntax. Templates are centralized in `quiz_app/messages.py`: enrollment (duration and minimum/cap), closure, question (number and deadline), STOP, correct answer/optional explanation, interim rankings and final results. Tied ranks share the same medal; final rankings include points by question. Long messages prefer paragraph or line boundaries when splitting. Question-bank content remains exactly as authored: use French questions and explanations for a fully French game.

Example question as sent to WhatsApp:

```text
🧠 *QUESTION 1 / 3*

Quelle est la capitale de la France ?

⏱️ Tu as *30 s* pour répondre.
✍️ Envoie *!r ta réponse*.

_Seule ta première réponse compte._
```

New outgoing messages contain only player-facing text. Correlation keys, sequence reservations and WhatsApp message identities remain local. Identical STOP messages in different rounds are distinguished by their native identities.

### Automatically enroll a test player

No manually entered participant name is required in automatic mode. Ensure WhatsApp is signed in and the target group has an empty composer, stop the local web service, and arrange for one **other account** to participate:

```sh
python -m scripts.validate_auto --group "Test" --join-seconds 180 --seconds 60
```

This command posts an enrollment announcement, accepts the first incoming `!join` using its stable native sender identity, closes enrollment and publishes a question. The answer-window limit is 180 seconds; use `--seconds 120` for a slower rehearsal. That player must send three separate messages in this exact order: `!r Paris`, `!r Londres`, `!r Paris`, before STOP. Commands use the current `.env` prefixes. The validator checks the complete native text segment, its author identity and order (nontext records are ignored), and verifies that only the first answer earns points. It then publishes the verified result and writes a receipt scoped to the explicitly selected group. Set `WHATSAPP_GROUP` to that same group before starting a native game.

A reply from the bot's own account, including the same account on a phone, is outgoing and cannot enroll. Incorrect, incomplete, edited or unexpected transcripts do not produce a successful validation receipt. Private evidence and write-ahead reservations remain under `data/diagnostics/`; an interrupted attempt is not automatically replayed. These are real group messages: use a dedicated group whose members expect the test.

### Play a complete real rehearsal

Use the normal game engine for multiple questions, intermediate scores and a final breakdown:

```sh
python -m scripts.play_rehearsal
```

Configure `WHATSAPP_GROUP`, `NB_PLAYERS_EXPECTED`, `MAX_PLAYERS`, `MAX_QUESTIONS`, `REGISTRATION_SECONDS`, `QUESTION_SECONDS` and `INTERVAL_SECONDS` in `.env`. The default bank is `data/questions.json`, resolved from the project directory. No command-line parameters are required. The command launches WhatsApp when necessary and opens the configured group automatically. Ensure its composer is empty, stop the web service, and have the configured number of other accounts ready. Everyone must send `!join` after enrollment opens.

`NB_PLAYERS_EXPECTED` is the minimum enrollment count, while `MAX_PLAYERS` is the cap. At the registration deadline, the engine closes enrollment and checks the complete conversation segment. Below the minimum, it announces cancellation and archives the game as cancelled without posting any question. Meeting the minimum starts the game, even below the cap; extra players do not end registration early. This rule also applies to dashboard games. The minimum must be an integer from 1 to `MAX_PLAYERS`; when omitted in older configurations or archives, it defaults to 1. A cancellation announcement with an uncertain delivery pauses for explicit recovery rather than being replayed.

The selected bank supplies the questions, limited by `MAX_QUESTIONS`. Players answer naturally with `!r their answer`; no predetermined reply sequence is required. Intermediate and final scores are published in WhatsApp and printed in the terminal.

Defaults come from `.env`; explicit command-line overrides apply only to this session snapshot. Every run creates a fresh archived game under `data/sessions/`. Stop with Ctrl+C; interrupted games are never automatically resumed or replayed. The dashboard's **WhatsApp · partie de test réelle** mode provides the same explicit rehearsal capability without game commands in the terminal. Neither rehearsal entry point creates a validation receipt or changes the validated-transport gate.

## Scoring

With `N` registered players and a correct-answer rank `r`:

```text
points = round_half_up(MAX_POINTS − (MAX_POINTS − MIN_POINTS) × (r − 1) / (N − 1))
```

For one player, a correct answer receives `MAX_POINTS`. Incorrect and absent replies receive zero. Only correct replies advance `r`; absent/incorrect players remain in `N`. At defaults, 50 players receive 100 for the first correct reply, 61 for the 25th and 20 for the 50th. Equal final totals share a competition rank (1, 1, 3). Final reports include each player's points per question and are split into bounded messages.

## Storage and recovery

`data/questions.json` is the private bank. Each `data/sessions/<id>.json` contains the settings/question snapshot, enrollment, immutable first observations, corrections, points, phase, deadlines and outgoing reservations. Simulation transcripts are also saved so inspection survives a restart.

Writes use a private temporary file, `fsync`, atomic replacement, a nonblocking file lock and a previous-good `.backup.json`. Corrupt files are never silently repaired or overwritten. A send is reserved as `pending` before publication and becomes `sent` only after confirmation.

After interruption, open **Historique et récupération**, enter the session ID and click **Ouvrir l’archive**. Loading keeps the game paused. **Vérifier et reprendre** checks every pending send against recoverable history before resuming the saved phase. Native sends have a private pre-send sequence reservation and a confirmed WhatsApp message identity in `data/native-deliveries.json`; these identifiers are never appended to public message text. Keep this private ledger with the session archives. Missing, duplicate or unconfirmed native identities block resumption. Older archives with visible markers remain readable. Check WhatsApp manually; if a reserved draft exists, review and send it yourself before verification, or cancel the game. Never edit the outbox statuses to force a replay. **Arrêter** cancels locally without publishing an extra message. Rehearsal archives retain their explicit rehearsal mode; they do not acquire validated status through recovery.

A collection incident retains the previous observations and does not announce a complete scoreboard. Images, stickers, voice notes, polls, other nontext types, empty text and deletion notices are ignored, including media captions that resemble answer commands. Deleting or editing an observed registration or reply does not interrupt the game: its first collected text and identity remain frozen, and a later message cannot replace a player's first answer. A message deleted before collection is simply ignored. Observed native sequence values preserve the order of retained deleted answers and newly collected messages across JSON recovery. Legacy archives without sequence values retain their snapshot order. Identity conflicts, duplicate sequences and missing question/STOP boundaries still require review. Storage failures pause the in-memory controller and must be resolved before a durable recovery. To restore a backup, stop the service, preserve the failed document, copy the validated backup to its original name, restart and load the archive through the interface.

## Architecture

```mermaid
flowchart TD
  UI[Local HTML / CSS / JavaScript] --> HTTP[FastAPI · loopback boundary]
  HTTP --> CONTROL[Serialized controller and timer]
  ENV[Private .env] --> SNAP[Validated game snapshot]
  BANK[Private question-bank JSON] --> SNAP
  SNAP --> ENGINE[Registration / question / STOP state machine]
  CONTROL --> ENGINE
  ENGINE --> RESERVE[Durable outgoing reservation]
  RESERVE --> AX[Native macOS accessibility sender]
  AX --> WHATSAPP[WhatsApp Desktop]
  WHATSAPP --> SOURCE[Existing local WhatsApp database · read-only]
  SOURCE --> CONFIRM[Native outgoing identity confirmation]
  SOURCE --> HISTORY[Complete native question / STOP segment]
  HISTORY --> GRADE[Deterministic correction and rank scoring]
  GRADE --> STORE[Atomic session JSON and backup]
  CONFIRM --> STORE
  ENGINE --> SIM[Deterministic simulator]
```

Python/Pydantic validate contracts; FastAPI serves the local control plane. PyObjC exposes Cocoa (`NSWorkspace` and clipboard integration), ApplicationServices (AX permissions, attributes and actions) and Quartz (foreground-checked composer focus and send-button clicks). Sending is confirmed against the native message database; a successful accessibility action alone is not proof of publication. Python’s `sqlite3` opens WhatsApp’s existing source with `mode=ro`, `query_only` and a consistent transaction. Group queries are exact and parameterized. Native message identifiers preserve distinct repeated texts; sender identifiers separate identical display names. After filtering nontext records, the reader rejects missing/tied sequence values and duplicated message identifiers. First observations remain immutable across edits or deletion; the final text segment is merged with retained observations using native sequence values.

Process discovery queries `NSRunningApplication.runningApplicationsWithBundleIdentifier` directly on every attachment, so opening or restarting WhatsApp does not depend on the workspace's cached application list. Foreground guards read WhatsApp's live [`AXFrontmost` attribute](https://developer.apple.com/documentation/applicationservices/kaxfrontmostattribute?language=objc), including before each posted mouse event. Activation waits for that confirmation instead of using a cached `NSWorkspace.frontmostApplication` value in HTTP worker threads. Startup polls use bounded timed waits and do not rely on a Cocoa worker-thread run loop. AppKit's time-varying application properties depend on main-run-loop updates; see [Apple's NSRunningApplication documentation](https://developer.apple.com/documentation/appkit/nsrunningapplication?language=objc). Missing or false foreground information still prevents native interaction.

Accessibility pagination remains a diagnostic fallback prototype. Its UI cells can be virtualized and reused, so it is not evidence that an entire history has been recovered. Production collection and send confirmation use the native database. Application locks, write-ahead reservations, atomic JSON replacement and backups remain separate from this read-only external source.

| File | Responsibility |
|---|---|
| `.env.example` | Fictional operational defaults |
| `questions.example.json` | Fictional question bank |
| `quiz_app/config.py` | Strict `.env` parsing, validation and private atomic saves |
| `quiz_app/models.py`, `errors.py` | Typed schemas and classified errors |
| `quiz_app/messages.py` | French player announcements, native WhatsApp styling and score presentation |
| `quiz_app/grading.py` | Command extraction, correction modes and matching evidence |
| `quiz_app/normalization.py` | Shared Unicode, whitespace, case and punctuation normalization |
| `quiz_app/numeric.py` | Exact decimal parsing and declared-unit validation |
| `quiz_app/scoring.py` | Decimal half-up points and tied standings |
| `quiz_app/live.py` | Read-only provisional scores, participant labels and confirmed totals |
| `quiz_app/history.py` | Boundaries, page overlap and immutable observations |
| `quiz_app/transport.py` | Transport interface and no-send simulator |
| `quiz_app/database_reader.py` | Read-only native source, stable identities, complete windows and send confirmation |
| `quiz_app/native.py` | Legacy accessibility metadata and traversal diagnostic |
| `quiz_app/ax_reader.py` | Read-only native permissions, tree, rows and scrolling |
| `quiz_app/scrolling.py` | Foreground-checked small wheel steps with verified table geometry |
| `quiz_app/ax_sender.py` | Empty-draft checks, clipboard preservation, exact send-button selection and confirmed sending |
| `quiz_app/engine.py` | Game phases, reservations, reports and recovery |
| `quiz_app/storage.py`, `repository.py` | Locks, atomic writes, backups and schema validation |
| `quiz_app/app.py`, `__main__.py` | Local HTTP endpoints and service launcher |
| `quiz_app/static/` | French responsive dashboard, typed settings form, safe DOM rendering and view helpers |
| `scripts/read_messages.py` | Fast read-only message-count diagnostic and optional private export |
| `scripts/probe_whatsapp.py` | Legacy read-only accessibility prototype |
| `scripts/validate_transport.py` | Explicit controlled native test in Test |
| `scripts/play_rehearsal.py` | Complete explicitly invoked native rehearsal with scores and JSON archives |
| `scripts/validate_auto.py` | Automatic native enrollment, known-order round and first-answer scoring validation |
| `scripts/check_coverage.py` | Exact Python line/branch quality gates |
| `tests/` | Rules, native fakes, recovery, storage, HTTP and large-game simulations |
| `tests/frontend/` | JavaScript helpers and dashboard interactions |
| `pyproject.toml` | Python tests, lint, typing and coverage configuration |
| `requirements*.txt` | Runtime and developer dependencies |
| `package.json`, `package-lock.json` | Reproducible frontend test/lint dependencies |
| `eslint.config.js`, `vitest.config.js` | JavaScript complexity and coverage gates |
| `.github/workflows/ci.yml` | macOS Python/JavaScript checks, without native messages |
| `.gitignore` | Private settings, games, logs and generated artifacts |
| `LICENSE` | MIT license |

## Developer checks

Python 3.12 and Node.js 24.15+:

```sh
python -m pip install -r requirements-dev.txt
npm ci
python -m pytest
python scripts/check_coverage.py
ruff check quiz_app scripts
ruff format --check quiz_app scripts
mypy quiz_app scripts
complexipy quiz_app scripts --max-complexity-allowed 10
npm run lint
npm test
```

Quality gates enforce 100% application lines, at least 90% Python/JavaScript branches, full JavaScript function coverage, and 100% corrector/scorer branches. Cognitive complexity is limited to 10 per Python function with [complexipy](https://complexipy.com/usage-guide/) and JavaScript function with [SonarJS](https://github.com/SonarSource/SonarJS). Tests use simulated native dependencies and never send WhatsApp messages. Coverage is evidence about executed paths, not a guarantee of correctness; see [branch coverage](https://coverage.readthedocs.io/en/6.5.0/branch.html).

Real transport validation remains a separate acceptance step. Keep private `.env`, bank, sessions, validation fixtures, diagnostics and message history out of Git.
