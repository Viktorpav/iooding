variable "namespace" {
  type = string
}

variable "vpc" {
  type = any
}

variable "key_name" {
  type = string
}

variable "k8smaster" {
  type = any
}

variable "k8snode" {
  type = any
}

variable "sg_k8smaster" {
  type = any
}

variable "sg_k8snode" {
  type = any
}

variable "instances_per_subnet" {
  description = "Number of EC2 instances(nodes)"
  type        = number
  default     = 5
}