"""Pure domain rules for Tracker.

This package holds product logic that has no database session, no FastAPI and no
I/O: schedule configuration, tracking modes, weight rules and the habit
configuration-history decision rule. Keeping it dependency-free means the rules
that are expensive to get wrong (weekly quotas, version planning) can be unit
tested directly, and it keeps services thin.

Layering:

* ``app/domain``   — pure rules and value objects (this package)
* ``app/services`` — use cases that read/write the database through a session
* ``app/api``      — HTTP wiring only
"""
