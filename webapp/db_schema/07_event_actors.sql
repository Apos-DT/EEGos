ALTER TABLE record_events ADD COLUMN actor_user_id INTEGER REFERENCES users(id);
