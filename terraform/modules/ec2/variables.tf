variable "namespace" {
  type = string
}

variable "vpc" {
  type = any
}

variable "key_name" {
  type = string
}

variable "ec2_public" {
  type = any
}

variable "sg_pub_id" {
  type = any
}

variable "sg_priv_id" {
  type = any
}