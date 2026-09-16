# Research project title

Replace this text with a one-sentence description of the research question.

## Reproducing the project

Document the software requirements and the single command needed to reproduce the analysis. Until the project has a one-command workflow, list the scripts in the exact order they should be run.

## Repository structure

| Directory | Purpose |
|---|---|
| `code/` | Scripts used to acquire, clean, analyze, and visualize data |
| `data/raw/` | Original source data; ignored by Git unless explicitly allowed |
| `data/derived/` | Data created by the project's code; ignored by Git unless explicitly allowed |
| `output/` | Generated figures, tables, and other results |
| `paper/` | Paper source files and rendered drafts |

## Working practices

- Keep the `main` branch in a usable state.
- Use GitHub issues to record consequential tasks, questions, and decisions.
- Use short-lived branches to test important alternatives, then record the conclusion in the related issue.
- Commit small, coherent changes with descriptive messages.
- Never commit passwords, API keys, restricted data, or personally identifiable information.
- Update this README whenever the reproduction steps or directory structure change.
