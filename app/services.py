"""Shared pension operations. No Flask request, session, or response dependencies.

Adapters authenticate callers before invoking these functions. Citizen reads and
withdrawals always require the authenticated mobile; officer operations are a
separate interface. Transaction-owning operations commit mutation and audit together.
"""
import os
import re
import random
import hashlib
import configparser
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "config", "app.ini"))
IST = ZoneInfo("Asia/Kolkata")
ACTIVE_STATUSES = ("PENDING", "APPROVED", "DEEMED_APPROVED")
SCHEME_DEADLINE = datetime.strptime(config.get("pension", "scheme_deadline"), "%Y-%m-%d %H:%M")
MIN_AGE = config.getint("pension", "min_age")
SLA_DAYS = config.getint("pension", "sla_days")
BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

def now_ist():
    """The portal's clock is Indian Standard Time regardless of where the server runs."""
    return datetime.now(IST).replace(tzinfo=None)


def get_db():
    from runtime_db import connect
    return connect(config)


def sanitize(value, maxlen=100):
    # Trim whitespace and cap at the column width, counting characters (not
    # bytes) so Assamese/Bangla names are stored intact.
    if value is None:
        return ""
    return value.strip()[:maxlen]


def hash_password(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


def new_application_no():
    return "SSP" + datetime.now().strftime("%y") + str(random.randint(100000, 999999))


def write_audit(cur, app_id, action, actor, note=""):
    cur.execute("INSERT INTO audit_log (application_id, action, actor, note, at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (app_id, action, actor, note, datetime.now()))


def parse_dob(raw):
    try:
        return datetime.strptime((raw or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def age_on(dob, on):
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def validate_application(data, doc_path):
    """Validate a complete application. Returns (errors, cleaned).

    `errors` is a list of plain-language problems (empty when valid);
    `cleaned` holds the normalised values ready for create_application().
    """
    errors = []
    cleaned = {
        "applicant_name": sanitize(data.get("applicant_name")),
        "village": (data.get("village") or "").strip(),
        "block": (data.get("block") or "").strip(),
        "gender": data.get("gender") or "",
        "marital_status": data.get("marital_status") or "",
        "husband_name": (data.get("husband_name") or "").strip(),
        "husband_employer": "",  # no longer collected (not a scheme requirement)
        "bank_account": re.sub(r"[\s-]", "", data.get("bank_account") or ""),
        "ifsc": re.sub(r"[\s-]", "", (data.get("ifsc") or "")).upper(),
        "doc_path": doc_path or "",
        "dob": None,
    }
    for label, key in (("full name", "applicant_name"), ("village", "village"),
                       ("block", "block"), ("bank account", "bank_account")):
        if not cleaned[key]:
            errors.append("%s is required" % label)
    if cleaned["block"] and cleaned["block"] not in BLOCKS:
        errors.append("block must be one of: " + ", ".join(BLOCKS))
    if cleaned["bank_account"] and not re.fullmatch(r"\d{9,18}", cleaned["bank_account"]):
        errors.append("bank account number must be 9 to 18 digits")
    if cleaned["ifsc"] and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", cleaned["ifsc"]):
        errors.append("IFSC must be 11 characters, e.g. SBIN0003077")
    dob = parse_dob(data.get("dob"))
    if dob is None:
        errors.append("date of birth must be given as DD/MM/YYYY")
    else:
        cleaned["dob"] = dob
        if age_on(dob, now_ist().date()) < MIN_AGE:
            errors.append("applicant must be %d years of age or above" % MIN_AGE)
    if not cleaned["doc_path"]:
        errors.append("age proof document is required")
    if now_ist() > SCHEME_DEADLINE:
        errors.append("the application window has closed")
    return errors, cleaned


def active_application(cur, mobile):
    """The applicant's current live application, if any."""
    cur.execute("SELECT id, application_no, status FROM applications "
                "WHERE mobile = %s AND status IN %s "
                "ORDER BY submitted_at DESC LIMIT 1", (mobile, ACTIVE_STATUSES))
    return cur.fetchone()


def create_application(cur, mobile, cleaned):
    """Insert a validated application; ensure the status-portal account exists.

    The caller commits. Returns (id, application_no).
    """
    app_no = new_application_no()
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            husband_name, husband_employer, village, block, bank_account, ifsc,
            doc_path, status, submitted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)
           RETURNING id""",
        (app_no, cleaned["applicant_name"], mobile, cleaned["dob"], cleaned["gender"],
         cleaned["marital_status"], cleaned["husband_name"], cleaned["husband_employer"],
         cleaned["village"], cleaned["block"], cleaned["bank_account"], cleaned["ifsc"],
         cleaned["doc_path"], datetime.now()))
    new_id = cur.fetchone()[0]

    # status portal account; password is DOB as DDMMYYYY per dept. circular
    portal_pass = cleaned["dob"].strftime("%d%m%Y")
    cur.execute("INSERT INTO portal_users (mobile, password_hash) VALUES (%s,%s) "
                "ON CONFLICT (mobile) DO NOTHING",
                (mobile, hash_password(portal_pass)))
    write_audit(cur, new_id, "SUBMIT", "applicant:%s" % mobile)
    return new_id, app_no


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


class DuplicateApplication(ValueError):
    def __init__(self, existing):
        self.existing = existing
        super().__init__("An active application already exists")


@contextmanager
def transaction():
    """Commit on success, roll back on failure, always close the connection."""
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


def submit_application(mobile, data, doc_path, *, cur=None):
    """Submit for a mobile already authenticated by the calling adapter.

    Optional cur joins the caller transaction; otherwise this function commits.
    SMS is sent by the adapter after commit. An advisory lock serializes submissions
    for the same mobile; the unique partial index protects every database writer.
    """
    if cur is None:
        with transaction() as owned_cur:
            return _submit_application(owned_cur, mobile, data, doc_path)
    return _submit_application(cur, mobile, data, doc_path)


def _submit_application(cur, mobile, data, doc_path):
    if not isinstance(mobile, str) or len(mobile) != 10 or not mobile.isdigit():
        raise ValidationError(["a verified 10-digit mobile number is required"])
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (mobile,))
    # Validate after lock acquisition, so a waiting request cannot bypass closing.
    errors, cleaned = validate_application(data, doc_path)
    if errors:
        raise ValidationError(errors)
    existing = active_application(cur, mobile)
    if existing:
        raise DuplicateApplication(existing)
    for _ in range(20):
        cur.execute("SAVEPOINT application_insert")
        try:
            result = create_application(cur, mobile, cleaned)
        except psycopg2.errors.UniqueViolation as exc:
            cur.execute("ROLLBACK TO SAVEPOINT application_insert")
            cur.execute("RELEASE SAVEPOINT application_insert")
            if exc.diag.constraint_name == "uq_app_application_no":
                continue
            if exc.diag.constraint_name == "uq_app_active_mobile":
                existing = active_application(cur, mobile)
                if existing:
                    raise DuplicateApplication(existing) from exc
            raise
        else:
            cur.execute("RELEASE SAVEPOINT application_insert")
            return result
    raise RuntimeError("Could not allocate a unique application number; try again")


def get_latest_application_id(mobile):
    with transaction() as cur:
        cur.execute("SELECT id FROM applications WHERE mobile = %s "
                    "ORDER BY submitted_at DESC LIMIT 1", (mobile,))
        row = cur.fetchone()
        return row[0] if row else None


def get_citizen_application(app_id, mobile):
    """Ownership is part of the query, including for missing/anonymous identities."""
    with transaction() as cur:
        cur.execute("SELECT application_no, applicant_name, mobile, dob, village, block, "
                    "bank_account, ifsc, status, submitted_at, decided_at "
                    "FROM applications WHERE id = %s AND mobile = %s", (app_id, mobile))
        return cur.fetchone()


def get_officer_application(app_id, officer_username, *, blocks=None, cur=None, for_update=False):
    """Existing web view is unchanged; agent callers pass an explicit allowed block set."""
    if not officer_username:
        raise ValueError("An authenticated officer is required")
    if cur is None:
        with transaction() as owned_cur:
            return get_officer_application(app_id, officer_username, blocks=blocks, cur=owned_cur, for_update=for_update)
    query = ("SELECT application_no, applicant_name, mobile, dob, gender, "
             "marital_status, village, block, bank_account, ifsc, doc_path, "
             "status, submitted_at, decided_at, decided_by FROM applications WHERE id = %s")
    params = [app_id]
    if blocks is not None:
        if not blocks:
            return None
        query += " AND block IN %s"
        params.append(tuple(blocks))
    if for_update:
        query += " FOR UPDATE"
    cur.execute(query, params)
    return cur.fetchone()


def get_audit(app_id):
    """Internal read: callers must authorize access to the application first."""
    with transaction() as cur:
        cur.execute("SELECT at, action, actor, note FROM audit_log "
                    "WHERE application_id = %s ORDER BY at ASC", (app_id,))
        return cur.fetchall()


def withdraw_pending_application(app_id, mobile):
    if not mobile:
        raise ValueError("An authenticated citizen is required")
    with transaction() as cur:
        cur.execute("UPDATE applications SET status = 'WITHDRAWN', decided_at = %s, "
                    "decided_by = 'APPLICANT' WHERE id = %s AND mobile = %s "
                    "AND status = 'PENDING' RETURNING application_no",
                    (datetime.now(), app_id, mobile))
        row = cur.fetchone()
        if row:
            write_audit(cur, app_id, "WITHDRAW", "applicant:%s" % mobile)
        return row[0] if row else None


def decide_application(app_id, new_status, officer_username, reason, *, blocks=None, cur=None):
    """One conditional update and its audit commit together, or neither does.

    Identity comes from the adapter's authenticated context, never request form data.
    Repeated or losing concurrent decisions return None without adding audit rows.
    """
    if not officer_username or len(officer_username) > 44:
        raise ValueError("An authenticated officer name of up to 44 characters is required")
    if new_status not in ("APPROVED", "REJECTED"):
        raise ValueError("Decision must be APPROVED or REJECTED")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A reason is required for approval or rejection.")
    if len(reason) > 500:
        raise ValueError("Decision reason must be at most 500 characters.")
    if cur is None:
        with transaction() as owned_cur:
            return decide_application(app_id, new_status, officer_username, reason, blocks=blocks, cur=owned_cur)
    query = ("UPDATE applications SET status = %s, decided_at = %s, decided_by = %s "
             "WHERE id = %s AND status = 'PENDING'")
    params = [new_status, datetime.now(), officer_username, app_id]
    if blocks is not None:
        if not blocks:
            return None
        query += " AND block IN %s"
        params.append(tuple(blocks))
    cur.execute(query + " RETURNING application_no", params)
    row = cur.fetchone()
    if row:
        write_audit(cur, app_id, new_status, "admin:%s" % officer_username, reason)
    return row[0] if row else None


def list_citizen_applications(mobile, blocks, limit=20, before_id=None):
    """Bounded owner-filtered history for agent channels, newest IDs first."""
    with transaction() as cur:
        cur.execute("SELECT id, application_no, applicant_name, block, status, submitted_at, "
                    "decided_at, bank_account FROM applications WHERE mobile=%s AND block IN %s "
                    "AND (%s IS NULL OR id < %s) ORDER BY id DESC LIMIT %s",
                    (mobile, tuple(blocks), before_id, before_id, min(max(limit, 1), 20)))
        return cur.fetchall()


def officer_queue_summary(blocks):
    """Aggregate only permitted blocks, using the existing server-clock SLA cutoff."""
    from datetime import timedelta
    with transaction() as cur:
        cur.execute("SELECT status,count(*) FROM applications WHERE block IN %s GROUP BY status", (tuple(blocks),))
        statuses = dict(cur.fetchall())
        cur.execute("SELECT block,count(*),min(submitted_at),count(*) FILTER (WHERE submitted_at < %s) "
                    "FROM applications WHERE block IN %s AND status='PENDING' GROUP BY block ORDER BY block",
                    (datetime.now() - timedelta(days=SLA_DAYS), tuple(blocks)))
        return statuses, cur.fetchall()


def list_officer_applications(blocks, *, status='PENDING', block=None, mobile=None, application_no=None, after_id=None, limit=20):
    """Bounded oldest-first queue. Every filter is intersected with the permitted blocks."""
    if not blocks:
        return []
    query = ("SELECT id,application_no,applicant_name,mobile,block,status,submitted_at "
             "FROM applications WHERE block IN %s")
    params = [tuple(blocks)]
    for column, value in [('status', status), ('block', block), ('mobile', mobile), ('application_no', application_no)]:
        if value is not None:
            query += " AND " + column + "=%s"
            params.append(value)
    if after_id is not None:
        query += (" AND (submitted_at,id) > (SELECT submitted_at,id FROM applications "
                  "WHERE id=%s AND block IN %s)")
        params.extend([after_id, tuple(blocks)])
    query += " ORDER BY submitted_at ASC,id ASC LIMIT %s"
    params.append(min(max(limit, 1), 20))
    with transaction() as cur:
        cur.execute(query, params)
        return cur.fetchall()
