variable "region" {
  default     = "us-east-1"
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