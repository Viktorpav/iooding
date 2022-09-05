module "networking" {
  source    = "./modules/networking"
  namespace = var.namespace
}

module "ec2" {
  source     = "./modules/ec2"
  namespace  = var.namespace
  vpc        = module.networking.vpc
  k8smaster  = module.ec2.k8smaster
  k8snode    = module.ec2.k8snode
  sg_k8smaster  = module.networking.sg_k8smaster
  sg_k8snode  = module.networking.sg_k8snode
  key_name   = module.ssh-key.key_name
}

module "ssh-key" {
  source    = "./modules/ssh-key"
  namespace = var.namespace
}