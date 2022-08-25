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