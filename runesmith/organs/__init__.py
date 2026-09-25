"""Mutable organs.

Each organ is a standalone, standard-library module with an entry point
(``run(view, cockpit)``). Organs are the surface the Kaizen engine may rewrite;
a rewritten organ becomes part of a new frozen generation only after it passes
qualification. The kernel never imports organ code: organs execute confined in
``organ_child.py`` and reach the world only through granted cockpit affordances.
"""
