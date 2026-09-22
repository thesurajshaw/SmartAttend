import pytest
from app.services.prediction_service import (
    get_status, get_classes_needed, get_classes_can_miss, 
    calculate_what_if, detect_declining_trend
)

def test_classes_needed_and_miss_exact_examples():
    # A, C, R, Current, Needed, CanMiss
    cases = [
        (28, 40, 0.75, 8, 0),
        (36, 50, 0.75, 6, 0),
        (41, 50, 0.75, 0, 4),
        (19, 25, 0.75, 0, 0),
        (30, 40, 0.75, 0, 0)
    ]
    
    for A, C, R, exp_needed, exp_miss in cases:
        needed = get_classes_needed(A, C, R)
        miss = get_classes_can_miss(A, C, R)
        assert needed == exp_needed, f"Failed needed for A={A}, C={C}, expected {exp_needed} got {needed}"
        assert miss == exp_miss, f"Failed miss for A={A}, C={C}, expected {exp_miss} got {miss}"

def test_edge_cases():
    # C = 0
    assert get_classes_needed(0, 0, 0.75) == 0
    assert get_classes_can_miss(0, 0, 0.75) == 0
    
    # A = 0
    assert get_classes_needed(0, 10, 0.75) == 30
    assert get_classes_can_miss(0, 10, 0.75) == 0
    
    # A = C
    assert get_classes_needed(10, 10, 0.75) == 0
    
    # R = 0
    assert get_classes_needed(5, 10, 0.0) == 0
    assert get_classes_can_miss(5, 10, 0.0) == 999
    
    # R = 1
    assert get_classes_needed(5, 10, 1.0) == "impossible"
    assert get_classes_needed(10, 10, 1.0) == 0

def test_status():
    R = 0.75
    warning = 0.05
    assert get_status(41, 50, R, warning) == 'Safe'
    assert get_status(19, 25, R, warning) == 'Warning'
    assert get_status(36, 50, R, warning) == 'Critical'

def test_what_if():
    # A=36, C=50 -> P=72% (Critical)
    # Attend 6 more -> A=42, C=56 -> P=75% (Warning)
    projected, status, verdict = calculate_what_if(36, 50, 0.75, 6, 'attend', 0.05)
    assert abs(projected - 0.75) < 0.001
    assert status == 'Warning'
    
    # A=41, C=50 -> P=82% (Safe)
    # Miss 4 more -> A=41, C=54 -> P=75.92% (Warning)
    projected, status, verdict = calculate_what_if(41, 50, 0.75, 4, 'miss', 0.05)
    assert abs(projected - 0.7592) < 0.001
    assert status == 'Warning'

def test_trend():
    assert detect_declining_trend([0.9, 0.8, 0.7, 0.6]) is True
    assert detect_declining_trend([1.0, 0.9, 0.8, 0.7]) is True
    assert detect_declining_trend([0.9, 0.8, 0.8, 0.7]) is False
    assert detect_declining_trend([0.6, 0.7, 0.8, 0.9]) is False
    assert detect_declining_trend([0.9, 0.8, 0.7]) is False
