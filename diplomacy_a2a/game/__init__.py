"""Game-state layer — thin wrapper around Meta's `diplomacy` library.

We do NOT reimplement Diplomacy rules. All adjudication (order
resolution, support cutting, convoy chains, dislodgments, retreats,
builds, etc.) is delegated to `diplomacy.Game`.
"""
