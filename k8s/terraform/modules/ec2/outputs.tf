output "k8smaster" {
  value = aws_instance.k8smaster.public_ip
}

output "k8snode" {
  value = aws_instance.k8snode.public_ip
}