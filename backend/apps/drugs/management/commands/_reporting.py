from apps.drugs.services import LoadStats


def print_stats(command, stats: LoadStats, *, label: str) -> None:
    out = command.stdout
    mode = "DRY RUN (nothing written)" if stats.dry_run else "committed"
    out.write(f"{label}: {mode}")
    out.write(f"  rows read : {stats.rows_read}")
    out.write(f"  created   : {stats.created}")
    if stats.updated:
        out.write(f"  updated   : {stats.updated}  (already present, values refreshed)")
    out.write(f"  skipped   : {stats.skipped_total}")
    for reason, count in stats.skipped.most_common():
        out.write(f"    - {reason}: {count}")
    for reason, count in stats.notes.most_common():
        out.write(f"  note      : {reason}: {count}")
    if stats.skipped_total:
        out.write("Skipped rows were NOT loaded. Fix the input or add the missing drugs, then re-run (safe to repeat).")