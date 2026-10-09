"""Durable, library-private chapter drafts; no media or copied source evidence."""
from sqlalchemy import Column, ForeignKey, Index, Integer, Table, Text, CheckConstraint


def add_memory_tables(metadata):
    stories = Table('access_memory_stories', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
        Column('author_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('revision', Integer, nullable=False),
        Column('content', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        Column('updated_at', Integer, nullable=False),
        CheckConstraint('revision > 0'))
    Index('ix_access_memory_library', stories.c.library_id, stories.c.updated_at, stories.c.id)
    revisions = Table('access_memory_revisions', metadata,
        Column('story_id', Text, ForeignKey('access_memory_stories.id'), primary_key=True, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        Column('editor_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('mutation_id', Text, nullable=False),
        Column('request_digest', Text, nullable=False),
        Column('content', Text, nullable=False),
        Column('occurred_at', Integer, nullable=False),
        CheckConstraint('revision > 0'))
    Index('ix_access_memory_mutation', revisions.c.editor_id, revisions.c.mutation_id, unique=True)
    return stories, revisions
