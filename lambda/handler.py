import json
import os
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timezone


BUCKET = os.environ["BUCKET_NAME"]
PROJECT = os.environ["PROJECT"]
URL = f"https://gamefound.com/api/public/projects/getCrowdfundingProject?urlName={PROJECT}"
HISTORY_KEY = f"{PROJECT}/history.json"
s3 = boto3.client("s3")


def handler(event, context):
    req = urllib.request.Request(URL, headers={"User-Agent": "gamefound-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)

    now = datetime.now(timezone.utc)
    key = f"{PROJECT}/{now.year:04d}/{now.month:02d}/{now.day:02d}/{now.hour:02d}-{now.minute:02d}.json"
    s3.put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")
    print(f"Saved {key} ({len(body)} bytes)")

    snapshot = {
        "datetime": now.isoformat(),
        "backerCount": data["backerCount"],
        "commentCount": data["commentCount"],
        "fundsGathered": data["fundsGathered"],
    }

    try:
        existing = s3.get_object(Bucket=BUCKET, Key=HISTORY_KEY)["Body"].read()
        history = json.loads(existing)
    except s3.exceptions.NoSuchKey:
        history = []

    history.append(snapshot)
    s3.put_object(
        Bucket=BUCKET,
        Key=HISTORY_KEY,
        Body=json.dumps(history).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache, max-age=0",
    )
    print(f"Updated {HISTORY_KEY} ({len(history)} points)")

    return {"key": key, "historyPoints": len(history)}
