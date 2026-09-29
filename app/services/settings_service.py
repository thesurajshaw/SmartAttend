"""
The admin-configurable rules, read from the `settings` table.

Every page that needs the pass mark reads it through here, so changing a
rule in the admin Settings screen takes effect everywhere at once.
"""

from app.models import Setting

# Used when the admin has not set a value yet.
DEFAULTS = {
    'required_attendance_percent': '0.75',  # 75% pass mark
    'warning_band_percent': '0.05',         # 5% amber band above the mark
    'session_lock_hours': '24',             # edit window before a session locks
}


def get_setting(key):
    """The stored value for `key`, or its default."""
    row = Setting.query.filter_by(key=key).first()
    return row.value if row else DEFAULTS.get(key)


def get_rules():
    """The pass mark and warning band as fractions, e.g. (0.75, 0.05)."""
    return (
        float(get_setting('required_attendance_percent')),
        float(get_setting('warning_band_percent')),
    )


def get_lock_hours():
    """How many hours a faculty member may edit a session before it locks."""
    return int(get_setting('session_lock_hours'))
