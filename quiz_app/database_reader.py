"""Read WhatsApp's own local database; never create or write application SQL storage."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from quiz_app.errors import QuizError
from quiz_app.models import Message

REFERENCE_DATE = datetime(2001, 1, 1, tzinfo=timezone.utc)
COLUMNS = """m.Z_PK, m.ZSORT, m.ZSTANZAID, m.ZTEXT, m.ZISFROMME, m.ZMESSAGEDATE,
COALESCE(NULLIF(g.ZCONTACTNAME,''),NULLIF(g.ZFIRSTNAME,'')),
COALESCE(NULLIF(g.ZMEMBERJID,''),NULLIF(m.ZFROMJID,''))"""
FROM = "FROM ZWAMESSAGE m LEFT JOIN ZWAGROUPMEMBER g ON g.Z_PK=m.ZGROUPMEMBER "


@contextmanager
def readonly(path: Path) -> Iterator[sqlite3.Connection]:
    """Open an existing source with read-only/query-only flags and fresh WAL visibility."""
    connection = None
    try:
        connection = sqlite3.connect(path.expanduser().resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        yield connection
    except sqlite3.Error as exc:
        raise QuizError(
            "SOURCE_UNAVAILABLE", "WhatsApp local source is unavailable or its schema changed"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def resolve_group(connection: sqlite3.Connection, group: str) -> int:
    """Require one exact active native group, never a fuzzy or first-result match."""
    rows = connection.execute(
        "SELECT Z_PK FROM ZWACHATSESSION WHERE ZPARTNERNAME=? AND ZSESSIONTYPE=1 AND COALESCE(ZREMOVED,0)=0",
        (group,),
    ).fetchall()
    if len(rows) != 1:
        raise QuizError("GROUP_AMBIGUOUS", "The source contains no unique active group with this exact name")
    return int(rows[0][0])


def timestamp(value: float | None) -> str:
    """Convert Cocoa reference-date seconds to UTC ISO text; reject invalid timestamps."""
    if value is None:
        return ""
    try:
        return (REFERENCE_DATE + timedelta(seconds=value)).isoformat()
    except (ValueError, OverflowError, TypeError) as exc:
        raise QuizError("HISTORY_INCOMPLETE", "Invalid native message timestamp") from exc


def parse_row(row: tuple[Any, ...], group_id: int) -> Message:
    """Keep stable message/sender identities, exact content and native timestamps."""
    key, order, stanza, body, outgoing, date, name, sender = row
    if sender and str(sender).endswith("@g.us"):
        sender = None
    identity = sha256(str(sender).encode()).hexdigest()[:24] if sender else ""
    label = str(name or f"Participant {identity[-4:]}") if identity else ""
    return Message(
        author="You" if outgoing else label,
        author_id="self" if outgoing else identity,
        body=str(body or ""),
        outgoing=bool(outgoing),
        timestamp=timestamp(date),
        fingerprint=f"db:{group_id}:{stanza or key}",
    )


def ordered_rows(rows: list[tuple[Any, ...]], group_id: int) -> list[Message]:
    """Reject missing/tied sequence values and duplicated stable message IDs before scoring."""
    order = [row[1] for row in rows]
    if None in order or len(set(order)) != len(order):
        raise QuizError("HISTORY_INCOMPLETE", "Native conversation order is unavailable or tied")
    messages = [parse_row(row, group_id) for row in rows]
    if len({message.fingerprint for message in messages}) != len(messages):
        raise QuizError("HISTORY_INCOMPLETE", "Duplicate native message identity")
    return messages


def contact_names(path: Path, senders: set[str]) -> dict[str, set[str]]:
    """Read labels only for scoped senders from the optional native contact source; reject schema failures."""
    contacts = path.expanduser().with_name("ContactsV2.sqlite")
    if not senders or not contacts.exists():
        return {}
    identifiers = sorted(senders | {sender.partition("@")[0] for sender in senders})
    placeholders = ",".join("?" for _ in identifiers)
    with readonly(contacts) as connection:
        rows = connection.execute(
            "SELECT ZWHATSAPPID,ZLID,COALESCE(NULLIF(ZFULLNAME,''),NULLIF(ZGIVENNAME,''),"
            "NULLIF(ZBUSINESSNAME,'')) FROM ZWAADDRESSBOOKCONTACT "
            f"WHERE ZWHATSAPPID IN ({placeholders}) OR ZLID IN ({placeholders})",
            identifiers + identifiers,
        ).fetchall()
    return index_contacts(rows)


def index_contacts(rows: list[tuple[Any, ...]]) -> dict[str, set[str]]:
    """Index available contact labels by native addresses; retain conflicts for explicit rejection."""
    names: dict[str, set[str]] = {}
    for phone, lid, name in rows:
        if not name:
            continue
        for identity in (phone, lid):
            if identity:
                names.setdefault(str(identity), set()).add(str(name))
    return names


def named_rows(rows: list[tuple[Any, ...]], path: Path) -> list[tuple[Any, ...]]:
    """Resolve readable native labels without using encoded push metadata or exposing sender addresses."""
    senders = {str(row[7]) for row in rows if row[7] and not row[4]}
    names = contact_names(path, senders)
    result = []
    for row in rows:
        sender = str(row[7] or "")
        labels = names.get(sender, set()) | names.get(sender.partition("@")[0], set())
        if len(labels) > 1:
            raise QuizError("AUTHOR_AMBIGUOUS", "Native contacts disagree about a sender's display name")
        label = next(iter(labels), row[6])
        result.append((*row[:6], label, row[7]))
    return result


def boundary(connection: sqlite3.Connection, group_id: int, marker: str) -> int:
    """Find one outgoing marker within the selected group; fail on absent/duplicate boundaries."""
    rows = connection.execute(
        "SELECT ZSORT FROM ZWAMESSAGE WHERE ZCHATSESSION=? AND ZISFROMME=1 AND instr(ZTEXT,?)>0",
        (group_id, marker),
    ).fetchall()
    if len(rows) != 1 or rows[0][0] is None:
        raise QuizError("HISTORY_INCOMPLETE", "An outgoing boundary is missing, duplicate or unordered")
    return int(rows[0][0])


class DatabaseReader:
    """Every operation uses a consistent fresh read transaction scoped to one exact group."""

    def __init__(self, path: Path, group: str) -> None:
        """Bind the existing WhatsApp source and group name without opening a write connection."""
        self.path = path
        self.group = group

    def recent(self, count: int) -> list[Message]:
        """Read the last requested messages, including nontext records, in native order."""
        if count < 1 or count > 10000:
            raise ValueError("Count must be between 1 and 10000")
        with readonly(self.path) as connection:
            group_id = resolve_group(connection, self.group)
            rows = connection.execute(
                "SELECT " + COLUMNS + FROM + "WHERE m.ZCHATSESSION=? "
                "ORDER BY m.ZSORT DESC,m.Z_PK DESC LIMIT ?",
                (group_id, count),
            ).fetchall()
            return ordered_rows(named_rows(list(reversed(rows)), self.path), group_id)

    def segment(self, start: str, stop: str | None = None) -> list[Message]:
        """Read the complete strict question/STOP interval without any UI traversal."""
        with readonly(self.path) as connection:
            group_id = resolve_group(connection, self.group)
            begin = boundary(connection, group_id, start)
            end = boundary(connection, group_id, stop) if stop is not None else None
            if end is not None and end <= begin:
                raise QuizError("HISTORY_INCOMPLETE", "STOP precedes its question")
            query = "SELECT " + COLUMNS + FROM + "WHERE m.ZCHATSESSION=? AND m.ZSORT>? "
            parameters: list[object] = [group_id, begin]
            if end is not None:
                query += "AND m.ZSORT<? "
                parameters.append(end)
            rows = connection.execute(query + "ORDER BY m.ZSORT,m.Z_PK", parameters).fetchall()
            return ordered_rows(named_rows(rows, self.path), group_id)


class DatabaseTransport:
    """Fast native database reads with a separately serialized accessibility sender."""

    def __init__(self, reader: DatabaseReader, sender: Callable[[str, str], None]) -> None:
        """Bind a scoped read-only source and a confirmed native publisher."""
        self.reader = reader
        self.sender = sender

    def preview(self, start: str) -> list[Message] | None:
        """Read a complete current prefix quickly so normal polling does not need scrolling."""
        return self.reader.segment(start)

    def segment(self, start: str, stop: str | None = None) -> list[Message]:
        """Recover a complete ordered interval from the database transaction."""
        return self.reader.segment(start, stop)

    def send(self, text: str, marker: str) -> None:
        """Publish once, then wait briefly for its durable native source boundary; never replay."""
        self.sender(text, marker)
        for _ in range(40):
            try:
                self.reader.segment(marker)
                return
            except QuizError as exc:
                if exc.code != "HISTORY_INCOMPLETE":
                    raise
                time.sleep(0.05)
        raise QuizError(
            "PUBLICATION_UNCERTAIN", "Outgoing marker has not appeared uniquely in the native source"
        )
