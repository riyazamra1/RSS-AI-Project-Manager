# Cross-Repository Automation

The internal Autopilot engine can inspect and orchestrate RSS repositories. GitHub Actions' default token is scoped to its own repository, so cross-repository work requires a separately configured credential.

Preferred credential: a GitHub App installation token with only the permissions required by the RSS repositories. A fine-grained personal access token is an alternative.

The automation secret is `RSS_AUTOPILOT_GITHUB_TOKEN`. Store it only as a GitHub Actions secret and never commit it.

Human approval remains required for destructive operations and releases.
