"""Strict immutable trade prefixes, tolerant only of empty JSON schema fields.

Pandas unions transaction columns: the first sale can add buy_date=null to all
earlier purchases. That is not a new fact about those earlier transactions.
Never normalize an actual price, quantity, time, reason or other non-null fact.
"""
from copy import deepcopy


def preserve_trade_prefix(previous,current,through,*,label):
    prefix=[t for t in current if str(t['date'])[:10]<=through]
    def facts(t):return {k:v for k,v in t.items() if v is not None}
    if len(prefix)!=len(previous) or current[:len(prefix)]!=prefix or any(facts(a)!=facts(b) for a,b in zip(previous,prefix)):
        raise ValueError('Prior committed trades changed; refuse rewrite: '+label)
    # Keep the exact original row shapes and values in the committed ledger.
    # In-place replacement also preserves aliases held by resume-state objects.
    current[:len(previous)]=deepcopy(previous)
    return current
