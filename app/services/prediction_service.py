import math

def get_status(A, C, R, warning_band=0.05):
    """
    Classifies the current attendance status.
    Safe: P >= R + warning_band
    Warning: R <= P < R + warning_band
    Critical: P < R
    """
    if C == 0:
        return 'Safe'
    
    P = A / C
    if P >= R + warning_band:
        return 'Safe'
    elif P >= R:
        return 'Warning'
    else:
        return 'Critical'

def get_classes_needed(A, C, R):
    """
    Finds the smallest integer x >= 0 such that (A + x) / (C + x) >= R.
    """
    if C == 0:
        return 0
    
    P = A / C
    if P >= R:
        return 0
        
    if R >= 1:
        return "impossible"
        
    estimate = (R * C - A) / (1 - R)
    x = max(0, math.ceil(estimate))
    
    while (A + x) / (C + x) < R:
        x += 1
        
    while x > 0 and (A + x - 1) / (C + x - 1) >= R:
        x -= 1
        
    return x

def get_classes_can_miss(A, C, R):
    """
    Finds the largest integer y >= 0 such that A / (C + y) >= R.
    """
    if C == 0:
        return 0
        
    if R == 0:
        return 999
        
    P = A / C
    if P < R:
        return 0
        
    estimate = (A - R * C) / R
    y = max(0, math.floor(estimate))
    
    while A / (C + y) >= R:
        y += 1
    y -= 1
    
    return max(0, y)

def calculate_what_if(A, C, R, n, action, warning_band=0.05):
    """
    What-if calculator. Action is 'attend' or 'miss'.
    Returns (projected_percentage, status, verdict_string)
    """
    if action == 'attend':
        new_A = A + n
        new_C = C + n
    else:
        new_A = A
        new_C = C + n
        
    if new_C == 0:
        return 0.0, 'Safe', "No classes conducted."
        
    projected = new_A / new_C
    status = get_status(new_A, new_C, R, warning_band)
    
    pct_str = f"{projected * 100:.2f}%"
    
    if action == 'attend':
        if status == 'Critical':
            verdict = f"After attending {n} more classes you will be at {pct_str} — still facing a shortage."
        elif status == 'Warning':
            verdict = f"After attending {n} more classes you will be at {pct_str} — meeting the minimum but in the warning band."
        else:
            verdict = f"After attending {n} more classes you will be at {pct_str} — above the minimum."
    else:
        if status == 'Critical':
            verdict = f"If you miss {n} classes you will drop to {pct_str} — falling into a shortage."
        elif status == 'Warning':
            verdict = f"If you miss {n} classes you will drop to {pct_str} — entering the warning band."
        else:
            verdict = f"If you miss {n} classes you will be at {pct_str} — remaining safe."
            
    return projected, status, verdict

def detect_declining_trend(weekly_percentages):
    """
    Trend is strictly decreasing: W1 > W2 > W3 > W4.
    """
    if len(weekly_percentages) < 4:
        return False
        
    recent = weekly_percentages[-4:]
    return recent[0] > recent[1] > recent[2] > recent[3]
