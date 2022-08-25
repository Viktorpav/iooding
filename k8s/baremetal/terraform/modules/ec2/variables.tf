variable "namespace" {
  type = string
}

variable "vpc" {
  type = any
}

variable key_name {
  type = string
}

variable "k8smaster" {
  type = any
}

variable "k8snode" {
  type = any
}

variable "sg_k8smaster_id" {
  type = any
}

variable "sg_k8snode_id" {
  type = any
}