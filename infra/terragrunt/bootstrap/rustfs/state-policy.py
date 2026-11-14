#!/usr/bin/env python3
"""Print a least-privilege RustFS IAM policy; this contains no credentials."""
import argparse
import json


def policy(bucket):
    root = f"arn:aws:s3:::{bucket}"
    prefix = "more-naive/prod/"
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": [root],
         "Condition": {"StringLike": {"s3:prefix": [prefix + "*"]}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
         "Resource": [root + "/" + prefix + "*/terraform.tfstate"]},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": [root + "/" + prefix + "*/terraform.tfstate.tflock"]},
    ]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bucket")
    print(json.dumps(policy(parser.parse_args().bucket), indent=2))
