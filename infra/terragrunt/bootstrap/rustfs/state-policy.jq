(env.RUSTFS_BUCKET | if type == "string" and test("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
 then . else error("RUSTFS_BUCKET required") end) as $bucket |
"arn:aws:s3:::" + $bucket as $root |
{
  Version: "2012-10-17",
  Statement: [
    {Effect: "Allow", Action: ["s3:ListBucket"], Resource: [$root],
     Condition: {StringLike: {"s3:prefix": ["more-naive/prod/*"]}}},
    {Effect: "Allow", Action: ["s3:GetObject", "s3:PutObject"],
     Resource: [$root + "/more-naive/prod/*/terraform.tfstate"]},
    {Effect: "Allow", Action: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     Resource: [$root + "/more-naive/prod/*/terraform.tfstate.tflock"]}
  ]
}
