module "networking" {
  source    = "./modules/networking"
  namespace = var.namespace
}

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
          "ec2:DescribeInstances",
          "ssm:Describe*",
          "ssm:GetParameter",
          "ssm:List*",
          "rds:DescribeDBInstances",
          "rds:ListTagsForResource"
        ],
        "Effect": "Allow",
        "Resource": "*"
      }
    ]
  })
}

module "ec2" {
  source     = "./modules/ec2"
  namespace  = var.namespace
  vpc        = module.networking.vpc
  ec2_private = module.ec2.private_ip
  sg_pub_id  = module.networking.sg_pub_id
  sg_priv_id = module.networking.sg_priv_id
  key_name   = module.ssh-key.key_name
}

module "ssh-key" {
  source    = "./modules/ssh-key"
  namespace = var.namespace
}

module "rds" {
  source     = "./modules/rds"
  namespace  = var.namespace
  vpc        = module.networking.vpc
  sg_id      = module.networking.sg_id
  sec_g_rds_id  = module.networking.sec_g_rds_id
}



