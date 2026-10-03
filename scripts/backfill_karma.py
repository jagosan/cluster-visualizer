#!/usr/bin/env python3
import sqlite3
import time

def backfill(db_path):
    print(f"Backfilling {db_path}...")
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        now = time.time()

        cur.execute(
            """INSERT OR REPLACE INTO session_model_usage 
               (session_id, model, billing_provider, billing_base_url, billing_mode, task, 
                api_call_count, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, 
                reasoning_tokens, estimated_cost_usd, actual_cost_usd, cost_status, cost_source, 
                first_seen, last_seen) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "20261003_chunkito_backfill", # session_id
                "qwen3.8-flash-next:262k",    # model
                "custom",                     # billing_provider
                "http://100.71.183.123:11434/v1", # billing_base_url
                "unknown",                    # billing_mode
                "",                           # task
                14,                           # api_call_count
                7836,                         # input_tokens
                32638,                        # output_tokens
                0,                            # cache_read_tokens
                0,                            # cache_write_tokens
                0,                            # reasoning_tokens
                0.0,                          # estimated_cost_usd
                0.0,                          # actual_cost_usd
                "estimated",                  # cost_status
                "local_hardware",             # cost_source
                now,                          # first_seen
                now                           # last_seen
            )
        )
        con.commit()
        con.close()
        print("Success.")
    except Exception as e:
        print("Failed:", e)

backfill("/home/jagosan/.hermes/state.db")
backfill("/home/jagosan/.hermes/profiles/jagular/state.db")
