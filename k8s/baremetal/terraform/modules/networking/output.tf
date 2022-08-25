output "vpc" {
  value = module.vpc
}

output "sg_k8smaster" {
  value = aws_security_group.allow_ssh_pub.id
}

output "sg_k8snode" {
  value = aws_security_group.allow_ssh_priv.id
}