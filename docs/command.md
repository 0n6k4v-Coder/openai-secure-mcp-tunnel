# Command

## Docker Commands

### Docker — Build
```bash
docker compose build
```

### Docker — Start
```bash
docker compose up -d
```

### Docker — Status
```bash
docker compose ps
```

### Docker — Logs
```bash
docker compose logs -f tunnel-client
```

### Docker — Stop
```bash
docker compose down
```

---

## Python Commands

### Auto-format + Auto-fix Linting
```bash
uv run ruff format . && \
uv run ruff check . --fix 
```

---

## Git Commands

### Git — Review Changes
```bash
git status --short && git diff HEAD
```