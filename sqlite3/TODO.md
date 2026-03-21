# SQLITE3 TODO

Open sqlite3-driver-specific follow-ups only.
Generic purego-gen issues belong in root [`TODO.md`](../TODO.md).

- [ ] Add aggregate-function registration on top of `sqlite3_create_function_v2`.
- [ ] Add broader DSN compatibility for mattn/go-sqlite3 options that are still intentionally out of scope in v1.
- [ ] Add extension-loading support with an explicit security posture.
- [ ] Add more complete time parsing/formatting compatibility with mattn/go-sqlite3.
- [ ] Add richer column metadata support when the raw layer grows to include origin/database/table-name APIs.
- [ ] Add WAL API (`sqlite3_wal_checkpoint_v2`, `sqlite3_wal_hook`) support.
- [ ] Add Backup API (`sqlite3_backup_*`) support.
