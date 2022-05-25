variable "region" {
  default     = "eu-central-1"
  description = "AWS region"
}

variable "namespace" {
  description = "The project namespace to use for unique resource naming"
  default     = "iooding"
  type        = string
}



