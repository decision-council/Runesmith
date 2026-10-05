# Security

Please report a vulnerability privately, not in a public issue:

- through GitHub's **Report a vulnerability** button on this repository's Security tab, or
- by e-mail to contact@aithinklab.com, with "Runesmith security" in the subject.

Say what you found, how to reproduce it, and which version (`python -m runesmith --version`) and operating system you used. We aim to answer within a few days.

Please do not include API keys, tokens or private project content in a report.

## Know the boundary

Runesmith runs self-modifiable organs in confinement, but that confinement uses a Python audit hook (PEP 578), which is not a hardened security boundary. Import generations only from sources you trust, or run Runesmith under an operating-system sandbox. Projects' own tests and code run on throwaway copies, which are not a security boundary either: only switch on test runs for projects you trust. There has been no external security audit.
