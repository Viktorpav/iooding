output "k8smaster" {
  value = aws_instance.k8smaster.public_ip
}

output "k8smaster_private_ip" {
  value = aws_instance.k8smaster.private_ip
}

output "k8snode" {
  value = join("", aws_instance.k8snode[*].id)
}