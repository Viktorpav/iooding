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
  sg_pub_id  = module.networking.sg_pub_id
 # sg_priv_id = module.networking.sg_priv_id
  key_name   = module.ssh-key.key_name
}

module "ssh-key" {
  source    = "./modules/ssh-key"
  namespace = var.namespace
}