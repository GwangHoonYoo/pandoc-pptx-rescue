# Evidence and interpretation

The comparison was executed on 2026-10-27 with official Pandoc 3.13, Python 3.12.13 and official LibreOffice 26.8.1.1 on macOS Apple Silicon. Public source references are downloaded from the original authors; see [fixtures.json](fixtures.json) for exact URLs, sizes and hashes. They are not redistributed here.

| Original source | Pandoc internal targets missing | Source parts restored by this CLI | Visual interpretation |
|---|---:|---:|---|
| [10085, LibreOffice reference](https://github.com/jgm/pandoc/issues/10085) | 20 | 20 | Title and body reappear after guarded title normalization plus dependency recovery |
| [9003, corporate reference](https://github.com/jgm/pandoc/issues/9003) | 2 | 2 | Native LibreOffice already displays content; no exclusive visual benefit established |
| [9421, Teams reference](https://github.com/jgm/pandoc/issues/9421) | 2 | 6, including transitive properties and relationships | Native LibreOffice already displays content; no exclusive visual benefit established |
| 9421, valid reference control | 0 | 0 | No title normalization or source restoration required |

The added files differ by mechanism. The LibreOffice reference has additional slide masters. The corporate reference has revision-history parts. The Teams reference has custom XML and dependent property parts. The tool retrieves those existing parts from the supplied reference rather than inventing replacements.

For the README's original 10085 reference and short included example, the native baseline PDF contains only `test` and `Test Slide`. The CLI output contains `Test Slide Deck`, `test`, `Test Slide` and `Test`, on two pages. Both rendered pages were visually inspected. The README image was composed from those actual PDFs.

Earlier research used the original 9421 Markdown as shared comparison content. The 9003 and 10085 complete author presentations were not reproduced. This is an original-reference input test, not confirmation from the original author's deployment or Microsoft PowerPoint.

## Existing alternatives

Current LibreOffice can re-save the corporate and Teams outputs to remove their missing-target references. That is an existing alternative, and this tool does not claim to uniquely restore their visible content.

On the tested 10085 input, re-saving the generated presentation with LibreOffice removes dangling references but does not recover the omitted title/body. Re-saving the reference before Pandoc also does not recover them. Source-part recovery alone restores the body; the demonstrated title needs the guarded `title` to `ctrTitle` placeholder adjustment before conversion.

## What remains unverified

Microsoft PowerPoint repair dialogs, complete layout fidelity, accessibility, charts, animation and real user adoption have not been verified. The research package validator still reports unreferenced parts after source recovery; zero missing internal targets is a narrower condition than full package conformance. No star-growth effect is inferred from the local comparisons.

The package tests use authored adversarial fixtures for failure handling. They are separate from original-input and consumer evidence.
