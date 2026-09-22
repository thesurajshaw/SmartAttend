import pytest
from app.services.attendance_service import get_attendance_metrics

def test_get_attendance_metrics():
    records = ['present', 'present', 'absent', 'late', 'excused', 'absent']
    # A = 2 present + 1 late = 3
    # C = 2 present + 2 absent + 1 late = 5 (excused is excluded)
    A, C = get_attendance_metrics(records)
    assert A == 3
    assert C == 5
