output "vpc" {
  value = module.vpc
}

output "sg_pub_id" {
  value = aws_security_group.allow_ssh_pub.id
}

output "sg_priv_id" {
  value = aws_security_group.allow_ssh_priv.id
}

output "sg_id" {
  value = aws_db_subnet_group.rds-sub-g.id
}

output "sec_g_rds_id" {
  value = aws_security_group.rds-sec-g.id
}

