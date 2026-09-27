# SupportHat

Local CLI-based support ticket system for the HatOS team.

## Quick Start

### Create a case

```bash
python -m supporthat create-case "HatOS won't boot" -p high -s email -a alice
```

### List cases

```bash
python -m supporthat list-cases
python -m supporthat list-cases --status open --assignee alice
```

### Show case details

```bash
python -m supporthat show-case 1
```

### Update a case

```bash
python -m supporthat update-case 1 --status in_progress --assignee bob
```

### JSON output

Add `--json` to any command for JSON output:

```bash
python -m supporthat --json list-cases
```

### Custom database location

```bash
python -m supporthat --db /path/to/support.db list-cases
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## Case Fields

- **id**: Auto-generated unique identifier
- **subject**: Brief description of the issue (required)
- **description**: Detailed information
- **status**: open, in_progress, pending, resolved, closed
- **priority**: low, normal, high, urgent
- **source**: Where the case came from (email, chat, etc.)
- **assignee**: Team member handling the case
- **created_at**: Timestamp when created
- **updated_at**: Timestamp of last update

## Storage

Cases are stored in a local SQLite database (`supporthat.db` by default).
Data persists across runs.
