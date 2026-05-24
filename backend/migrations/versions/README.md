This directory keeps recent Alembic revisions at the top level.

Older revisions are archived under subdirectories such as `archive/`.
Alembic is configured with `recursive_version_locations = true`, so archived
revisions remain part of the migration graph and existing databases can still
upgrade normally.
