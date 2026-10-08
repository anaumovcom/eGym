"""Digital twin of the real path (plan 14 §7.1): mechanics, drive, bus, users.

The twin is the ground truth for identification tests: it is built from a
known (random) ``PlantParams``; calibration procedures must recover them
through the same ``TorqueDrive`` contract that the real drives use.
"""
