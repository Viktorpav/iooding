variable "region" {
  default     = "eu-central-1"
  description = "AWS region"
}

variable "profile" {
  default     = "cloud_user"
  description = "AWS profile"
}

variable "namespace" {
  description = "The project namespace to use for unique resource naming"
  default     = "iooding"
  type        = string
}

variable "k8smaster" {
  description = "The kubernetes infrastucture for unique resource naming"
  default     = "k8smaster"
  type        = string
}

variable "k8snode" {
  description = "The kubernetes infrastucture for unique resource naming"
  default     = "k8snode"
  type        = string
}



