## Branches and commits

### Branch names

`<type>/<short-description>`, lowercase, words separated by hyphens.
Examples: `feat/health-endpoint`, `fix/cors-origins`, `docs/api-contract`.

### Commit messages

`<type>(<scope>): <what changed>`
Example: `feat(backend): add health endpoint`

| Type | Use for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Adding or changing tests |
| `refactor` | Restructuring code without changing behavior |
| `chore` | Maintenance with no effect on app behavior: `.gitignore`, config, tooling, dependencies |

Scopes: `backend`, `frontend`, `contracts`, `ml`, `docs`.

### Rules

- Never commit directly to `main`; open a pull request.
- One branch per PR, one logical piece of work per PR.
- Every PR needs one approval from someone other than its author.
- Delete the branch after merging.
- Never commit secrets (`.env`, private keys, API keys).
