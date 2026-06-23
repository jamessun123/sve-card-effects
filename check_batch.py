#!/usr/bin/env python3
import json
import sys

from batch_utils import make_client

batch_id = sys.argv[1] if len(sys.argv) > 1 else "batch_6a39c9235acc8190bf3537f26f42ba1c"
client = make_client()
batch = client.batches.retrieve(batch_id)
print("status:", batch.status)
print("errors:", batch.errors)
if batch.errors:
    print(json.dumps(batch.errors.model_dump() if hasattr(batch.errors, "model_dump") else batch.errors, indent=2))
