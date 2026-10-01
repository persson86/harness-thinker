# Task boundary fixtures

All people, statements, sources and markers here are synthetic. No private vault,
conversation, credentials or account configuration is used.

The Python tests copy these sources into fresh temporary workspaces. Checkpoint
JSON goes into a separate temporary inputs directory. Task state and exports are
outside that workspace, under private temporary directories. Every CLI operation
runs in a fresh subprocess with isolated HOME, XDG and native provider config.

Task A's initial approval report is superseded by a human correction; a later
checkpoint must retain that correction and the analysis-only authority boundary.
Task B is more recent but must never be selected instead of the requested ID.
Source A deliberately includes an unsupported statement and an untrusted command:
byte identity must not certify either as truth or authorization. Historical
frontmatter must remain byte-for-byte unchanged.

These fixtures test deterministic CLI contracts. They do not test an agent's
semantic reasoning, actual provider authentication, human utility or time saved.

`fault-before-replace.py` is loaded only by an isolated child process to terminate
it immediately before an OS atomic replacement of its selected task document.
The test verifies the fault marker, last committed revision, successful retry and
receipt deduplication. It does not simulate a disk-power failure or certify all
filesystem durability behavior.
