"""
The prediction engine: pure arithmetic, no database.

Every function takes three numbers and returns an answer:

    attended   how many classes the student actually attended  (A)
    conducted  how many classes counted toward their record    (C)
    required   the pass mark as a fraction, e.g. 0.75 for 75%  (R)

Because nothing here touches the database, each rule below can be
read, checked by hand, and unit-tested on its own.
"""

import math

# Percentages are computed with floats, so a value that should be exactly
# 30 can come out as 29.999999999999996. Rounding to 6 decimal places before
# taking a ceiling or floor removes that noise without changing real answers.
_PRECISION = 6


def percentage(attended, conducted):
    """Attendance as a percentage (0-100). No classes yet means 0%."""
    if conducted == 0:
        return 0.0
    return attended / conducted * 100


def status_for_fraction(fraction, required, warning_band=0.05):
    """
    Which zone a ready-made fraction (0 to 1) falls in.

        Safe      at or above the pass mark plus the warning band
        Warning   at or above the pass mark, but inside the band
        Critical  below the pass mark

    With a 75% pass mark and a 5% band: Safe is >= 80%, Warning is
    75-80%, Critical is below 75%.
    """
    if fraction >= required + warning_band:
        return 'Safe'
    if fraction >= required:
        return 'Warning'
    return 'Critical'


def get_status(attended, conducted, required, warning_band=0.05):
    """
    Which zone the student is in, from their raw counts.
    A student with no classes yet is Safe -- they have not missed anything.
    """
    if conducted == 0:
        return 'Safe'
    return status_for_fraction(attended / conducted, required, warning_band)


def get_classes_needed(attended, conducted, required):
    """
    How many classes in a row must the student attend to reach the pass mark?

    Attending x more classes raises both counts, so we need the smallest
    whole x where:

        (attended + x) / (conducted + x) >= required

    Rearranged to isolate x:

        attended + x       >= required * (conducted + x)
        x - required * x   >= required * conducted - attended
        x * (1 - required) >= required * conducted - attended
        x                  >= (required * conducted - attended) / (1 - required)

    So the answer is that value rounded up. Returns 0 if the student is
    already at or above the mark, and the string 'impossible' if the mark
    is 100% (no amount of attending undoes a past absence).
    """
    if conducted == 0:
        return 0

    if attended >= required * conducted:
        return 0

    if required >= 1:
        return 'impossible'

    exact = (required * conducted - attended) / (1 - required)
    return max(0, math.ceil(round(exact, _PRECISION)))


def get_classes_can_miss(attended, conducted, required):
    """
    How many classes can the student skip and still stay at the pass mark?

    Missing y classes leaves 'attended' unchanged but grows 'conducted',
    so we need the largest whole y where:

        attended / (conducted + y) >= required

    Rearranged to isolate y:

        attended            >= required * (conducted + y)
        attended / required >= conducted + y
        y                   <= attended / required - conducted

    So the answer is that value rounded down, never below 0. A student
    already under the mark can miss nothing.
    """
    if conducted == 0:
        return 0

    if required == 0:
        return 999  # No requirement at all: effectively unlimited.

    if attended < required * conducted:
        return 0

    exact = attended / required - conducted
    return max(0, math.floor(round(exact, _PRECISION)))


# Wording for each (action, resulting status) pair, used by calculate_what_if.
_VERDICTS = {
    ('attend', 'Critical'): "After attending {n} more classes you will be at {pct} — still facing a shortage.",
    ('attend', 'Warning'): "After attending {n} more classes you will be at {pct} — meeting the minimum but in the warning band.",
    ('attend', 'Safe'): "After attending {n} more classes you will be at {pct} — above the minimum.",
    ('miss', 'Critical'): "If you miss {n} classes you will drop to {pct} — falling into a shortage.",
    ('miss', 'Warning'): "If you miss {n} classes you will drop to {pct} — entering the warning band.",
    ('miss', 'Safe'): "If you miss {n} classes you will be at {pct} — remaining safe.",
}


def calculate_what_if(attended, conducted, required, n, action, warning_band=0.05):
    """
    "What happens if I attend / miss the next n classes?"

    Attending adds to both counts; missing adds only to the denominator.
    Returns (projected_fraction, status, plain_English_verdict).
    """
    if action == 'attend':
        new_attended, new_conducted = attended + n, conducted + n
    else:
        new_attended, new_conducted = attended, conducted + n

    if new_conducted == 0:
        return 0.0, 'Safe', "No classes conducted."

    projected = new_attended / new_conducted
    status = get_status(new_attended, new_conducted, required, warning_band)
    verdict = _VERDICTS[(action, status)].format(n=n, pct=f"{projected * 100:.2f}%")

    return projected, status, verdict


def guidance_message(status, needed, can_miss, required):
    """
    The one-line advice shown on the student's dashboard and subject page.
    Kept here so both pages always say exactly the same thing.
    """
    mark = f"{required * 100:.0f}%"

    if status == 'Critical':
        if needed == 'impossible':
            return "Your attendance is too low to recover to the required threshold."
        return f"You need to attend your next {needed} consecutive classes to reach {mark}."

    if status == 'Warning':
        return "You are at the minimum. You cannot miss any more classes right now."

    if can_miss > 0:
        plural = 'es' if can_miss != 1 else ''
        return f"You can safely miss up to {can_miss} more class{plural} and still stay above {mark}."
    return f"You are at exactly {mark}. Do not miss any classes."


def detect_declining_trend(weekly_percentages):
    """
    True when the last four weeks each dropped from the week before,
    e.g. 90% -> 85% -> 80% -> 70%. Fewer than four weeks is never a trend.
    """
    if len(weekly_percentages) < 4:
        return False

    w1, w2, w3, w4 = weekly_percentages[-4:]
    return w1 > w2 > w3 > w4
