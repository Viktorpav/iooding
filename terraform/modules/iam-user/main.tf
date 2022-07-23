resource "aws_iam_user" "ssm" {
  name = "${var.namespace}-boto3"
}

resource "aws_iam_access_key" "acck" {
  user = aws_iam_user.ssm.name
}

resource "aws_iam_user_policy" "ssm_policy" {
  name = "${var.namespace}-ssm-policy"
  user = aws_iam_user.ssm.name

  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Action": [
          "ssm:Describe*",
          "ssm:Get*",
          "ssm:List*",
          "rds:DescribeDBInstances",
          "rds:ListTagsForResource"
        ],
        "Effect": "Allow",
        "Resource": "arn:aws:rds:eu-central-1:994168006738:db:*"
      }
    ]
  })
}