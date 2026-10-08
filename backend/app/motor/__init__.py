"""Motor control v2 (plan/14–16).

Pure core: ``units``, ``profile``, ``estimation``, ``force``, ``supervisor``,
``calibration.fit`` — no I/O, time and randomness are injected. Raw drive
units exist only in ``drive``. Internally everything is N, mm, mm/s, s;
up is positive.
"""
