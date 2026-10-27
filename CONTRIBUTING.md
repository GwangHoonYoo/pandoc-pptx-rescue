# Contributing

Open an issue in this repository with the exact Pandoc/Python/consumer versions, command, JSON result and expected versus observed content. Include a minimal public reference and Markdown input only when they can be shared. Remove private source metadata before posting.

Run `python -m unittest discover -s tests -v`. Changes to package recovery also need a same-input comparison and a native consumer check for any claimed visual improvement. A zero missing-target count alone does not establish complete presentation fidelity.

AI-assisted contributions are welcome when the commands were actually executed, evidence scope is stated, and generated claims are checked. Preserve original files, exact-source provenance and unsupported-case behavior. Do not claim independent adoption from operator tests.
