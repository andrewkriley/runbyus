CREATE TABLE IF NOT EXISTS principal (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS label (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS space (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS space_label (
  space_id TEXT NOT NULL,
  label_id TEXT NOT NULL,
  PRIMARY KEY (space_id, label_id)
);

CREATE TABLE IF NOT EXISTS membership (
  space_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  role TEXT NOT NULL,
  since TEXT NOT NULL,
  until TEXT
);

CREATE TABLE IF NOT EXISTS channel_account (
  id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  external_user_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  label_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  title TEXT,
  enabled_channels TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  author_kind TEXT NOT NULL,
  author_id TEXT NOT NULL,
  origin_channel TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_item (
  id TEXT PRIMARY KEY,
  parent_id TEXT,
  root_id TEXT NOT NULL,
  thread_id TEXT,
  space_id TEXT NOT NULL,
  label_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  trigger_kind TEXT NOT NULL,
  trigger_source TEXT NOT NULL,
  agent TEXT NOT NULL,
  state TEXT NOT NULL,
  route_id TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS route (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL,
  tier TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  risk TEXT NOT NULL,
  confidence REAL,
  reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  args_hash TEXT NOT NULL,
  args_json TEXT NOT NULL,
  risk_tier TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  decided_by TEXT,
  decision TEXT,
  decided_channel TEXT,
  decided_at TEXT
);

CREATE TABLE IF NOT EXISTS event (
  id TEXT PRIMARY KEY,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_state (
  work_item_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ao_trace (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ao_span (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT,
  content TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
