"""공통 로그 형식 (계획서 7절): 메시지마다 JSON 한 줄."""
import json
import os
import time
import uuid
from datetime import datetime, timezone


class V2XLog:
    def __init__(self, node, path=None):
        self.node = node
        self.path = path or os.path.join("logs", f"{node}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, "a", buffering=1)

    def write(self, msg_type, sender, decision, reason="NONE", auth_status="NOT_CHECKED",
              fail_step=None, decode_status="VALID", t_start=None):
        rec = {
            "traffic": {"message_id": uuid.uuid4().hex[:12], "message_type": msg_type,
                        "sender_id": sender,
                        "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")},
            "auth": {"auth_status": auth_status, "fail_step": fail_step},
            "checks": {"decode_status": decode_status, "semantic_status": "NOT_CHECKED"},
            "result": {"decision": decision, "reason": reason},
            "meta": {"processing_time_ms": round((time.perf_counter() - t_start) * 1000, 3)
                     if t_start else None,
                     "node": self.node, "process_state": "RUNNING"},
        }
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
