"""Owner-controlled runtime preference; changes remain auditable."""
def llm_enabled(cur):
    cur.execute('SELECT llm_enabled FROM finance.v_classification_settings')
    return cur.fetchone()['llm_enabled']


def lock(cur):
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('finance-llm-toggle'))")
