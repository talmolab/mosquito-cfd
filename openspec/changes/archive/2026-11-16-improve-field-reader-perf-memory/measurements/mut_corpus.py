"""Write the corpus mutant table (task 8.1, corpus rows, after the _is_dir skip-list) as JSON."""

import json
import sys

F = "src/mosquito_cfd/field_surrogate/corpus.py"
T = "tests/test_field_surrogate_corpus.py::"
SKIP = T + "test_an_entry_path_is_dir_would_skip_is_still_skipped"
PROP = T + "test_failing_entry_type_check_propagates_unless_path_is_dir_ignored_it"
ERRNOS = "    {errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP}\n"
CALL = "        return entry.is_dir()\n"
FILTER = "            if not (match and _is_dir(entry)):\n                continue\n"
rows = [
    ("os.scandir -> iterdir + Path.is_dir",
     [["with os.scandir(run) as entries:",
       'with __import__("contextlib").nullcontext(run.iterdir()) as entries:']],
     ["test_listing_costs_one_scandir_and_no_per_entry_stat"]),
    ("entry.is_dir() -> Path(entry.path).is_dir()",
     [[CALL, "        return Path(entry.path).is_dir()\n"]],
     ["test_listing_costs_one_scandir_and_no_per_entry_stat"]),
    ("is_dir(follow_symlinks=False)",
     [[CALL, "        return entry.is_dir(follow_symlinks=False)\n"]],
     ["test_symlinked_plotfile_directory_counts", "test_listing_follows_symlinks_on_every_os"]),
    ("_is_dir bypassed (entry.is_dir() direct)",
     [["if not (match and _is_dir(entry)):", "if not (match and entry.is_dir()):"]], [SKIP]),
    ("ENOENT dropped", [[ERRNOS, "    {errno.ENOTDIR, errno.EBADF, errno.ELOOP}\n"]], [SKIP]),
    ("ENOTDIR dropped", [[ERRNOS, "    {errno.ENOENT, errno.EBADF, errno.ELOOP}\n"]], [SKIP]),
    ("EBADF dropped", [[ERRNOS, "    {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}\n"]], [SKIP]),
    ("ELOOP dropped", [[ERRNOS, "    {errno.ENOENT, errno.ENOTDIR, errno.EBADF}\n"]], [SKIP]),
    ("winerror 21 dropped", [["frozenset({21, 123, 1921})", "frozenset({123, 1921})"]], [SKIP]),
    ("winerror 123 dropped", [["frozenset({21, 123, 1921})", "frozenset({21, 1921})"]], [SKIP]),
    ("winerror 1921 dropped", [["frozenset({21, 123, 1921})", "frozenset({21, 123})"]], [SKIP]),
    ("winerror check removed",
     [["            or getattr(exc, \"winerror\", None) in _NOT_A_DIRECTORY_WINERRORS\n", ""]],
     [SKIP]),
    ("ValueError not caught",
     [["    except ValueError:\n        return False\n", ""]], [SKIP]),
    ("raise -> return False (swallow every OSError)",
     [["            return False\n        raise\n", "            return False\n        return False\n"]],
     [PROP]),
    ("found[step] = entry",
     [["found[step] = run / entry.name", "found[step] = entry"]],
     ["test_noncanonical_step_resolves_with_one_listing"]),
    ("found[step] = entry.path",
     [["found[step] = run / entry.name", "found[step] = entry.path"]],
     ["test_noncanonical_step_resolves_with_one_listing"]),
    ("with dropped",
     [["with os.scandir(run) as entries:", "if entries := os.scandir(run):"]],
     ["test_scan_closes_the_listing_on_the_duplicate_raise"]),
    ("_configs cache bypassed",
     [["if self._configs_cache is None:", "if True:"]],
     ["test_corpus_pass_reads_the_manifest_once",
      "test_manifest_is_parsed_from_disk_only_once_per_instance"]),
    ("duplicate check before the is_dir filter",
     [[FILTER, "            if not match:\n                continue\n"],
      ["            found[step] = run / entry.name\n",
       "            if _is_dir(entry):\n                found[step] = run / entry.name\n"]],
     ["test_non_directory_entries_never_duplicate_or_resolve"]),
    ("sorted dropped from steps()",
     [["return sorted(_scan(self.run_dir(config_id)))",
       "return list(_scan(self.run_dir(config_id)))"]],
     ["test_steps_sort_numerically_not_lexically"]),
    ("duplicate message in listing order",
     [['", ".join(sorted((found[step].name, entry.name)))',
       '", ".join((found[step].name, entry.name))']],
     ["test_duplicate_step_directories_raise"]),
    ("[0-9] -> \\d", [['re.compile(r"plt([0-9]+)")', 're.compile(r"plt(\\d+)")']],
     ["test_only_ascii_digit_whole_name_plotfiles_count"]),
    ("fullmatch -> match, with $ restored",
     [['re.compile(r"plt([0-9]+)")', 're.compile(r"plt([0-9]+)$")'],
      ["_PLT_PATTERN.fullmatch(entry.name)", "_PLT_PATTERN.match(entry.name)"]],
     ["test_only_ascii_digit_whole_name_plotfiles_count"]),
]
table = [{"name": n, "file": F, "edits": e,
          "tests": [t if t.startswith("tests/") else T + t for t in ts]} for n, e, ts in rows]
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(table, fh, indent=1)
print(len(table), "mutants")
