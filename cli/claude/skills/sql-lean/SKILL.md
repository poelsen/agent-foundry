---
name: sql-lean
description: Keeps database code cheap at full data size. Load before writing, changing or reviewing code that runs SQL or processes rows from a database (sqlite3, SQLAlchemy, psycopg, an ORM).
---

# sql-lean — database access that stays cheap at full size

Code that reads a database is written and tested against a few items, where
every version is fast. The slow versions are correct. They cost too much only
when the same code runs over the whole table, over every key, or on every
request. Most of that cost sits in the code around the queries, and less of it
in the SQL. These are the questions to settle while writing such code, ordered
roughly by how often each one is the cause.

## Before writing

1. **Find the sizes.** The row counts of the tables you touch, and how many
   items (keys, files, requests) the code runs for. Look in the project's
   database notes, or count on real data. If you cannot find out, say which
   size you assumed.
2. **State the multiplication.** How many times does this run at full size,
   and what does one run cost in statements, rows read, payloads decoded and
   connections opened? Give the product in your reply. A call that takes
   10 ms is nothing once and 25 minutes over 150,000 items.
3. **Look for the path that already exists.** A batch reader, a cached index,
   a stored result. Search the module and its neighbours before writing a new
   reader. A slow new path beside a fast existing one is a common outcome.

## While writing

### Do each piece of work once

Work whose result is the same for every item gets done again per item, per
call or per request. This is the most frequent cause.

- Whatever does not depend on the loop variable moves out of the loop:
  opening a connection, building a lookup, loading a reference table,
  resolving configuration, parsing a payload.
- A function that is cheap on its own can hide such work. Before calling one
  inside a loop, read what it does on each call. Examples: it opens its own
  connection, it rebuilds an index and reads one key from it, it validates a
  cache by checking files on disk.
- Decode a stored payload once and pass the result on. Two readers that each
  fetch and decode the same row do the work twice.
- A result that depends only on stored data that has not changed is computed
  once and kept, for the run or for the request. Key what you keep on the
  inputs that change it. A wider key discards the result when nothing it
  depends on moved.

### Read only what the caller uses

- Look at what the consumer does with the result. Select those columns and
  decode those fields.
- Answer the question that was asked. Examples: "is there any such row" is an
  existence query, and "the value on one date" is one row; neither is a full
  read followed by a test in Python.
- Leave expensive detail to the request that inspects it. A table view does
  not need the history behind every cell.

### Narrow to the wanted keys in the query

- When the caller wants some keys, the query filters to them. Filtering in
  Python pays for every row, and so does any aggregation, ranking or decoding
  that runs before the filter.
- Pass a large key set as an indexed temporary table, or as chunked `IN`
  lists, and join on it so the query is driven from the small side.
- A job that runs repeatedly skips unchanged input in SQL, before anything is
  read or decoded. A stored high-water mark is one way.

### Write the set form first

- Write the reader for a set of keys. The single-key function calls it with
  one key, so the two cannot disagree.
- One query per item in a loop is a join or an `IN` not yet written. That
  includes lookups hidden behind a property or `__getitem__`.

### Make sure an index serves each probe

An index on the column is not enough: the planner has to be able to use it
for this lookup. Read the plan on real-size data (`EXPLAIN QUERY PLAN` in
SQLite, `EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL) and look for scans of the
large table.

Reasons an existing index goes unused. These are examples, not the full list:

- A function wraps the indexed column, as in `UPPER(col) = ?`. Normalise the
  value when it is written and compare it directly.
- The compared types differ. In SQLite, `CREATE TABLE AS SELECT` can leave a
  column untyped, and a typed probe then cannot use the key. Cast in the
  select.
- The probe uses a later column of a composite index without the leading
  ones.
- The index does not hold the selected columns, and the planner picks another
  one that does.

Also:

- Temporary and staging tables have only the indexes you create. One that is
  joined to or probed per row needs one.
- The predicates of `DELETE` and `UPDATE` need an index as much as those of
  `SELECT`.
- A correlated subquery runs once per outer row. Index its inner lookup, or
  rewrite it as a join or a window.
- Create indexes once, after a bulk load.

### Write in batches

One transaction per batch or stage, and `executemany` or `INSERT … SELECT`
in place of single inserts. A commit, a checkpoint or a new connection per row
costs far more than the row.

## Before calling it done

- **Measure at full size.** Run it against real-size data, on a copy when it
  writes. Report the time, the number of statements and connections, and the
  rows read; give before and after when you changed existing code. A test on
  ten rows says nothing about cost.
- **Show the plan** of each new query on a large table.
- **Check the results are unchanged** when the change was for speed: compare
  old and new output on real data.
- **Pin it with a test** where the project does that. Examples: the plan has
  no scan of the large table, or the statement count for N items does not
  grow with N.
- If you could not measure, say so, and say what you expect and why.

## Keep it in proportion

Where the sizes are small and will stay small, say so and write the simple
version. A job that reprocesses everything on each run is often right while
the data is small; note how its cost grows with the data and leave the
incremental machinery until it is needed.
