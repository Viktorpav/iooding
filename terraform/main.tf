module "networking" {
  source    = "./modules/networking"
  namespace = var.namespace
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

module "iam-user" {
  source    = "./modules/iam-user"
  namespace = var.namespace
}


module "rds" {
  source     = "./modules/rds"
  namespace  = var.namespace
  vpc        = module.networking.vpc
  sg_id      = module.networking.sg_id
  sec_g_rds_id  = module.networking.sec_g_rds_id
}



