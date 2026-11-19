import json


def report_progress(stage: str, progress: int, stage_progress: int, message: str) -> None:
    print(
        json.dumps(
            {
                "type": "progress",
                "stage": stage,
                "progress": progress,
                "stage_progress": stage_progress,
                "message": message,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
