"""Response-coding error taxonomy (lab wiki + bsliang_rpcode2trials.m).

Tag strings use ``/`` separators; multiple derived errors are joined with ``/`` in order
LATE_RESP, NOISY_BSL, EARLY_RESP.
"""

# Lexical NoDelay: generic response error
RESP_ERR = "RESP_ERR"

# Lexical Delay: parsed from bsliang_errors.txt (input codes use '_' separators)
ERR_TASK_YN_REP = "ERR_TASK/YN_REP"
ERR_TASK_REP_YN = "ERR_TASK/REP_YN"
ERR_RESP_REP_WRO = "ERR_RESP/REP_WRO"
ERR_RESP_REP_MIS = "ERR_RESP/REP_MIS"
ERR_RESP_YN_YN = "ERR_RESP/YN_YN"
ERR_RESP_YN_NY = "ERR_RESP/YN_NY"
NOISE = "NOISE"

# Derived in both tasks
LATE_RESP = "LATE_RESP"
NOISY_BSL = "NOISY_BSL"
EARLY_RESP = "EARLY_RESP"
CORRECT = "CORRECT"
